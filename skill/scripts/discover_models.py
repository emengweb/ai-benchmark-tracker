# -*- coding: utf-8 -*-
"""AI Benchmark Tracker 运行时模型发现适配器。

数据源：
- 主源：OpenRouter Models API（https://openrouter.ai/api/v1/models），公开 JSON，
  提供模型 id/名称/上下文长度/多模态/定价（per-token 字符串，按 $/1M 转换）/发布时间；
- 可选热度提示：OpenRouter 月榜单页（https://openrouter.ai/rankings?view=month）
  为 Next.js 动态页面，无稳定公开 JSON 接口，此处仅做“首次出现顺序”正则提取作为
  启发式排序；提取不到时回退到目录内“最新发布优先”的确定性排序，并明确标注来源，
  绝不冒充月榜排名。

重要边界：
- 本适配器只发现模型元数据（机构/特性/定价/链接）。GPQA Diamond、SWE-bench Verified、
  MMLU-Pro 等分数不会从此接口获得，输出记录中故意不包含分数 -> 导出器会将其标记为
  “数据不完整，未参与综合排名”，等待人工/Agent 从可核验来源补录。
- 本地永久存储去重：每次运行联网获取一次目录，与本地快照/注册表对比，本地已有的
  模型不再获取任何数据，仅对 is_new=true 的新模型入库、整理、取评分；评分采集完成
  后同样永久存入本地（注册表含评分来源 URL）。
- 网络失败时回退到本地快照（openrouter_models_cache.json），并在 provenance 中标注
  stale=True；快照也没有则报错退出，不编造任何模型。
"""
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request

from model_taxonomy import (
    classify_institution,
    resolve_company_key,
    company_aliases,
    institution_display,
)
from skill_config import cache_enabled, load_config
from export_benchmark_excel import canonical_model_key

OPENROUTER_MODELS_API = "https://openrouter.ai/api/v1/models"
OPENROUTER_RANKINGS_URL = "https://openrouter.ai/rankings?view=month"
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openrouter_models_cache.json")
RANKINGS_HINT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openrouter_rankings_hint.json")
DEFAULT_LIMIT = 20
USER_AGENT = "ai-benchmark-tracker/1.0 (local skill adapter)"


def http_get(url, timeout=25, retries=3):
    """带回退与 Retry-After 的 GET；成功返回 (payload_str, None)，失败返回 (None, err)。"""
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html;q=0.9"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            retry_after = e.headers.get("Retry-After") if e.headers else None
            last_err = f"HTTP {e.code} {e.reason}"
            if e.code == 429 and retry_after:
                try:
                    time.sleep(min(float(retry_after), 30))
                    continue
                except ValueError:
                    pass
            if e.code in (500, 502, 503, 504):
                time.sleep(min(2 ** attempt + random.random(), 15))
                continue
            break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = str(e)
            time.sleep(min(2 ** attempt + random.random(), 15))
    return None, last_err


def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_cache(cache):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"WARNING: 缓存写入失败: {e}", file=sys.stderr)


def _snapshot_ids():
    """本地目录快照中已见过的 base model_id 集合（判断"新模型"的依据之一）。"""
    cache = load_cache()
    ids = set()
    for e in (cache or {}).get("data") or []:
        mid = (e.get("id") or "").split(":")[0]
        if mid:
            ids.add(mid.lower())
    return ids


def _registry_name_keys():
    """注册表已收录模型的规范名集合（基线模型没有 OpenRouter id，按名称判定）。"""
    keys = set()
    try:
        from export_benchmark_excel import DEFAULT_REGISTRY_PATH, canonical_model_key, load_or_init_registry
        for m in load_or_init_registry(DEFAULT_REGISTRY_PATH):
            ck = canonical_model_key(m.get("name"))
            if ck:
                keys.add(ck)
    except Exception as e:
        print(f"WARNING: 读取注册表失败，新模型判定仅按目录快照 id: {e}", file=sys.stderr)
    return keys


def fetch_catalog():
    """每次运行联网获取一次 OpenRouter 目录（仅此一次调用）。

    返回 (models_payload_list, provenance, fatal_error, new_ids)：
    - 成功：与本地快照对比得到 new_ids（本地没有的 base model_id），快照覆盖保存；
      后续"入库/整理/取评分"只针对本地没有的项目；
    - 失败：回退本地永久存储快照（stale=True），离线也能出报告。
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev_ids = _snapshot_ids()

    payload, err = http_get(OPENROUTER_MODELS_API)
    if payload:
        try:
            data = json.loads(payload).get("data", [])
        except ValueError as e:
            err = f"响应解析失败: {e}"
        else:
            new_ids = sorted({
                (e.get("id") or "").split(":")[0].lower()
                for e in data if e.get("id")
            } - prev_ids)
            cache = {
                "fetched_at": now_iso,
                "source": OPENROUTER_MODELS_API,
                "http_status": 200,
                "model_count": len(data),
                "data": data,
            }
            save_cache(cache)
            return data, {"fetched_at": now_iso, "stale": False, "cache_hit": False,
                          "error": None}, None, new_ids

    # 网络失败 -> 本地永久存储快照兜底
    cache = load_cache()
    if cache and isinstance(cache.get("data"), list):
        print(f"WARNING: OpenRouter 获取失败（{err}），使用本地永久存储快照（{cache.get('fetched_at')}）", file=sys.stderr)
        return cache["data"], {
            "fetched_at": cache.get("fetched_at", "unknown"),
            "stale": True,
            "cache_hit": True,
            "error": err,
        }, None, []

    return None, {"fetched_at": now_iso, "stale": True, "cache_hit": False, "error": err}, (
        f"无法获取 OpenRouter 模型目录且本地无永久存储快照: {err}"
    ), []


def fetch_rankings_hint():
    """尽力而为：按月榜页面提取 'provider/model' 引用（首次出现顺序）作热度排序。

    网络优先；成功后永久存至 openrouter_rankings_hint.json；失败时回退本地快照，
    保证弱网环境下热度排序仍可用。均失败返回 None。
    """
    payload, err = http_get(OPENROUTER_RANKINGS_URL, timeout=25, retries=1)
    if payload:
        seen = []
        seen_set = set()
        for m in re.finditer(r'href="/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"', payload):
            variant = m.group(2)
            if ":" in variant or "?" in variant or "=" in variant:
                continue
            ref = f"{m.group(1).lower()}/{variant.lower()}"
            if ref in seen_set:
                continue
            seen_set.add(ref)
            seen.append(ref)
        if seen:
            try:
                with open(RANKINGS_HINT_PATH, "w", encoding="utf-8") as f:
                    json.dump({"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                               "refs": seen}, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
            return seen, None
        err = "rankings 页面未提取到模型引用"
    # 网络失败/未提取到 -> 本地快照兜底
    try:
        with open(RANKINGS_HINT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        refs = data.get("refs") or []
        if refs:
            return refs, None
    except Exception:
        pass
    return None, f"rankings 页面获取失败且本地无快照: {err}"


def per_million(price_str):
    if price_str is None:
        return None
    try:
        return round(float(price_str) * 1_000_000, 6)
    except (TypeError, ValueError):
        return None


def derive_attribute(name):
    """从模型名称推导定位属性（与基线属性列同一内容形式：定位描述词）。

    注意：多模态/免费/商用不进属性列——工作簿已有"是否多模态"与"参考定价"
    专列，属性列只承载其他列表达不了的定位信息（如基线的"全尺寸旗舰""高吞吐 MoE"）。
    目录元数据推不出的定位（开源权重/端云结合等）不编造，回退"通用"。
    """
    low = str(name or "").lower()
    tier = None
    if re.search(r"(?:^|[^a-z])(?:pro|max|ultra|flagship|large|plus)(?:[^a-z]|$)", low):
        tier = "旗舰"
    elif re.search(r"(?:^|[^a-z])(?:flash|mini|lite|turbo|nano|small|tiny|air)(?:[^a-z]|$)|\d(?:\.\d+)?b(?:[^a-z]|$)", low):
        tier = "轻量"
    purpose = None
    if re.search(r"(?:^|[^a-z])(?:mt|translate|translation)(?:[^a-z]|$)", low):
        purpose = "翻译"
    elif re.search(r"preview|experimental", low) or re.search(r"(?:^|[^a-z])exp(?:[^a-z]|$)", low):
        purpose = "预览"
    bits = [b for b in (tier, purpose) if b]
    return "".join(bits) if bits else "通用"


def normalize_catalog_entry(entry, fetched_at):
    mid = entry.get("id", "")
    base_id = mid.split(":")[0]
    provider_slug = base_id.split("/")[0] if "/" in base_id else ""
    name = entry.get("name") or base_id
    # OpenRouter name 常带 "Provider: " 前缀，剥离以避免与基线同名模型重复入库
    # （前缀与 provider slug 归一比较：Z.ai -> z-ai）
    if ":" in name:
        prefix = name.split(":", 1)[0].strip().lower().replace(" ", "-").replace(".", "-")
        if prefix == provider_slug.lower() or prefix in provider_slug.lower():
            name = name.split(":", 1)[1].strip()
    name = name.strip()
    arch = entry.get("architecture") or {}
    in_mods = arch.get("input_modalities") or []
    out_mods = arch.get("output_modalities") or []
    mods = set(list(in_mods) + list(out_mods))
    multimodal = bool(mods & {"image", "audio", "video", "file"})

    ctx = entry.get("context_length")
    if not ctx:
        top_provider = entry.get("top_provider") or {}
        ctx = top_provider.get("context_length")

    pricing = entry.get("pricing") or {}
    price_in = per_million(pricing.get("prompt"))
    price_out = per_million(pricing.get("completion"))

    created = entry.get("created")
    release_date = ""
    if isinstance(created, (int, float)) and created > 0:
        release_date = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m")

    region, key = classify_institution(provider_slug)
    institution = institution_display(key, fallback=provider_slug or "未知机构")

    # 属性：从名称推导定位描述（旗舰/轻量/预览/翻译），形式与基线属性列一致；
    # 多模态/定价信息由专列承载，不在属性列重复
    attribute = derive_attribute(name)

    ctx_text = f"{ctx:,}" if ctx else "未知"
    mod_text = "/".join(sorted(mods)) if mods else "text"
    notes = (
        f"OpenRouter 目录运行时发现（base: {base_id}，上下文 {ctx_text}，"
        f"模态 {mod_text}）。Benchmark 评分待从可核验来源采集，未核验分数以 ⚠ 标注。"
    )

    return {
        "name": name,
        "institution": institution,
        "attribute": attribute,
        "region": region,
        "multimodal": multimodal,
        "release_date": release_date,
        "price_input": price_in,
        "price_output": price_out,
        "notes": notes,
        "source_url": f"https://openrouter.ai/{base_id}",
        "discovered_via": {
            "source": "openrouter_models_api",
            "model_id": mid,
            "canonical_slug": entry.get("canonical_slug"),
            "fetched_at": fetched_at,
        },
    }


def resolve_company_filter(company):
    """company -> 匹配函数(record) -> bool；未命中规则表则按原始子串匹配。"""
    if not company:
        return None
    key, _display = resolve_company_key(company)
    if key:
        aliases = company_aliases(key)
        def match(record):
            slug = str(record.get("discovered_via", {}).get("model_id", "")).split(":")[0].lower()
            inst = str(record.get("institution", "")).lower()
            if aliases and any(a in slug for a in aliases):
                return True
            return any(a in inst for a in aliases)
        return match
    raw = str(company).strip().lower()
    def raw_match(record):
        slug = str(record.get("discovered_via", {}).get("model_id", "")).lower()
        inst = str(record.get("institution", "")).lower()
        return raw in slug or raw in inst
    return raw_match if raw else None


def main():
    parser = argparse.ArgumentParser(description="运行时发现 AI 模型（OpenRouter 目录）")
    parser.add_argument("--scope", choices=["all", "domestic", "international"], default="all",
                        help="地域范围：all（默认）/ domestic / international")
    parser.add_argument("--company", default=None,
                        help="公司/机构过滤，如 openai / deepseek / 智谱")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"输出候选数量上限（默认 {DEFAULT_LIMIT}）")
    parser.add_argument("--use-rankings", action="store_true",
                        help="尝试以 OpenRouter 月榜页面作热度排序启发（尽力而为，失败自动回退）")
    parser.add_argument("--include-variants", action="store_true",
                        help="保留 (batch)/(free) 等同模型变体；默认只取每模型主条目")
    parser.add_argument("--no-cache", action="store_true",
                        help="本次忽略本地永久存储：全部候选视为新增（等价于 cache.enabled=false 的单次行为）")
    parser.add_argument("--output", default=None,
                        help="JSON 写入路径；缺省输出到 stdout")
    args = parser.parse_args()

    ignore_store = args.no_cache or not cache_enabled()
    catalog, prov, fatal, new_ids = fetch_catalog()
    if fatal:
        print(f"ERROR: {fatal}", file=sys.stderr)
        sys.exit(3)
    fetched_at = prov["fetched_at"]
    catalog_source = "openrouter_api" if not prov.get("cache_hit") else "local_snapshot_fallback"

    raw_records = [normalize_catalog_entry(e, fetched_at) for e in catalog]
    if not args.include_variants:
        # 默认剔除同模型变体（:batch/:free 等），避免榜单被重复条目淹没
        raw_records = [r for r in raw_records
                       if ":" not in (r.get("discovered_via") or {}).get("model_id", "")]

    # 与本地永久存储对比去重：base model_id 不在本地快照 且 规范名不在注册表 => 本地没有
    # 本地已有的不再获取任何数据；只有 is_new=true 的项目需要入库/整理/取评分
    if ignore_store:
        for r in raw_records:
            r["is_new"] = True
        print("[no-cache] 已忽略本地永久存储：全部候选视为新增（本次会重新取评分）", file=sys.stderr)
    else:
        known_ids = _snapshot_ids()
        known_names = _registry_name_keys()
        for r in raw_records:
            base_id = (r.get("discovered_via") or {}).get("model_id", "").split(":")[0].lower()
            ck = canonical_model_key(r["name"])
            r["is_new"] = bool(base_id) and base_id not in known_ids and ck not in known_names
        new_n = sum(1 for r in raw_records if r["is_new"])
        print(f"[store] 目录 {len(catalog)} 条与本地永久存储对比：新增 {new_n} 条"
              f"（仅新增入库/整理/取评分），其余复用本地已存信息", file=sys.stderr)

    # 排序：月榜启发（优先）或 最新发布优先（回退）
    ranking_source = "openrouter_catalog_latest_first_fallback"
    hint = None
    if args.use_rankings:
        hint, hint_err = fetch_rankings_hint()
        if hint:
            ranking_source = "openrouter_monthly_rankings_heuristic"
        else:
            print(f"WARNING: {hint_err}，回退到目录最新发布优先排序", file=sys.stderr)
        if hint is None:
            hint = []

    slug_of = lambda r: (r.get("discovered_via") or {}).get("model_id", "").split(":")[0].lower()
    if ranking_source.startswith("openrouter_monthly_rankings"):
        order = {ref: i for i, ref in enumerate(hint)}
        raw_records.sort(key=lambda r: order.get(slug_of(r), 10 ** 9))
    else:
        # 无 created 的排最后；其余按发布时间倒序（最新在前）
        def created_of(r):
            try:
                return datetime.strptime(r["release_date"], "%Y-%m").timestamp()
            except Exception:
                return 0.0
        raw_records.sort(key=lambda r: created_of(r), reverse=True)

    # 过滤：地域 + 公司
    records = raw_records
    if args.scope != "all":
        records = [r for r in records if r["region"] == args.scope]
    company_match = resolve_company_filter(args.company)
    if company_match:
        records = [r for r in records if company_match(r)]

    records = records[:max(0, args.limit)]

    if not records:
        print(
            f"WARNING: 范围筛选（scope={args.scope}, company={args.company or '无'}）"
            f"未命中任何模型（目录总量 {len(catalog)}）。",
            file=sys.stderr,
        )

    summary = {
        "scope": args.scope,
        "company": args.company,
        "limit": args.limit,
        "catalog_source": catalog_source,
        "new_count": sum(1 for r in records if r.get("is_new")),
        "new_models": [r["name"] for r in records if r.get("is_new")],
        "catalog_count": len(catalog),
        "selected_count": len(records),
        "ranking_source": ranking_source,
        "rankings_heuristic_used": ranking_source.startswith("openrouter_monthly_rankings"),
        "provenance": prov,
        "note": ("目录每次联网获取一次并与本地永久存储对比去重：is_new=true 表示本地没有的项目，"
                 "仅这些需要入库/整理/取评分；本地已有的直接复用注册表数据（含评分与来源）。"
                 "Benchmark 分数从可核验来源采集后通过 --add-model 补录"),
    }
    result = {"summary": summary, "models": records}

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"OUTPUT_PATH:{args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    # 状态摘要走 stderr，便于管道使用 stdout
    print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()