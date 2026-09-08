# -*- coding: utf-8 -*-
"""Benchmark 后备评分源适配器（benchmark_sources.py）。

在声称来源无法核验（403 / JS 渲染 / 页面无值）时，从下列权威/聚合跑分源获取
标准化分数观测，作为兜底候选值（不自动升级为已核验，需人工复核后采纳）：

| 适配器 | 数据源 | 覆盖指标 | 类型 |
| --- | --- | --- | --- |
| artificial_analysis | https://artificialanalysis.ai/models/<slug>（RSC 数据流） | GPQA Diamond, MMLU-Pro | aggregator(权威) |
| openrouter_indices | https://openrouter.ai/api/v1/models benchmarks.artificial_analysis | AA 三指数(辅助，不进三项基准) | aux |

已探测但不可用（如实记录，勿再尝试）：
- LMArena API（lmarena.ai/api/*）→ 403；
- OpenCompass 司南（rank.opencompass.org.cn/api/*）→ SPA 壳，无公开 JSON；
- Scale AI SWE-bench Pro HF space（data/dataset.parquet）→ 实为评测任务数据集
  （repo/instance_id/patch 列），不是模型成绩，违反"数据集≠成绩接口"原则；
- swebench.com / labs.scale.com/leaderboard → 动态渲染，无稳定 JSON。

使用：
  python benchmark_sources.py                          # 全部模型 x 全部适配器
  python benchmark_sources.py --models "Kimi K3,GPT-6 Astra"
  python benchmark_sources.py --output backup_scores.json

观测（Observation）统一字段：model_display / metric / value(0-100) / source /
source_type / source_url / fetched_at / notes。每个适配器独立失败隔离，
结果附带 status 摘要（ok / unavailable / not_found / redirect ...）。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from discover_models import http_get

CACHE_DIR = os.path.join(os.getcwd(), ".verify_cache")
OPENROUTER_MODELS_API = "https://openrouter.ai/api/v1/models"
SOURCE_TYPES = {"artificial_analysis": "aggregator", "openrouter_indices": "aux"}
MAX_WORKERS = 6          # 单适配器并发上限
PAGE_CACHE_TTL = 86400   # 后备源页面缓存有效期（秒）


def _page_cache_get(key):
    """命中返回 (body, final_url)；过期/缺失返回 None。"""
    path = os.path.join(CACHE_DIR, f"bs_{key}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("fetched_at", 0) > PAGE_CACHE_TTL:
            return None
        return data.get("body"), data.get("final_url")
    except Exception:
        return None


def _page_cache_set(key, body, final_url):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"bs_{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.time(), "body": body, "final_url": final_url}, f)
    except OSError:
        pass


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


# 包含匹配允许的后缀边界：仅同模型的推理配置/免费变体；pro/batch/mini 等是
# 不同模型或变体，禁止借用基础模型的后备值
_ALLOWED_SUFFIXES = ("high", "xhigh", "max", "low", "medium", "thinking", "free", "preview")


def _contained(short, long_):
    """short 是否为 long_ 的完整前缀且边界是允许的配置词/结束。"""
    i = long_.find(short)
    if i < 0:
        return False
    rest = long_[i + len(short):]
    if not rest:
        return True
    return any(rest == w or rest.startswith(w) for w in _ALLOWED_SUFFIXES)


def names_match(a, b):
    """归一化名称匹配：完全相等，或较长者包含较短的完整核心名（≥6 字符）。

    阈值 6 + 边界词白名单避免家族前缀/变体误配：
    - "glm53" 不匹配 "glm53flash"（Flash 是另一模型）；
    - "gpt6astra" 不匹配 "gpt6astrapro"/"gpt6astrabatch"（Pro/batch 不借用基础值）；
    - "claudeopus5" 匹配 "claudeopus5high"（High 是同模型的推理配置）。
    """
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 6 and _contained(na, nb):
        return True
    if len(nb) >= 6 and _contained(nb, na):
        return True
    return False


def fetch_body(url, timeout=30):
    body, err = http_get(url, timeout=timeout, retries=2)
    return body, err


def _get_with_final(url, timeout=30):
    """GET 并返回 (body, final_url, err)，用于检测家族页重定向。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace"), r.geturl(), None
    except urllib.error.HTTPError as e:
        return None, url, f"HTTP {e.code}"
    except Exception as e:
        return None, url, str(e)


# ---------------------------------------------------------------------------
# 适配器 1：Artificial Analysis 模型详情页（RSC 流解析）
# ---------------------------------------------------------------------------
def aa_slug(model_name):
    return re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")


def fetch_artificial_analysis(model_name, fresh=False):
    """抓取 https://artificialanalysis.ai/models/<slug>，解析 RSC 中的 gpqa/mmmuPro。

    防家族页误配：跟随重定向后若最终 URL 的 slug 与请求不一致（如 /models/glm-5-3-flash
    重定向到 /models/glm-5-3），拒绝采用该页数据。
    成功结果带磁盘缓存（24h TTL；fresh=True 时绕过缓存强制抓取并回写）。
    返回 (observations, status)。
    """
    slug = aa_slug(model_name)
    url = f"https://artificialanalysis.ai/models/{slug}"
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    body = final_url = None
    err = None
    if not fresh:
        cached = _page_cache_get(key)
        if cached is not None:
            body, final_url = cached
    if body is None:
        body, final_url, err = _get_with_final(url)
        if body is not None and err is None:
            _page_cache_set(key, body, final_url)
    if body is None:
        return [], {"source": "artificial_analysis", "model": model_name, "status": "unavailable",
                    "error": err, "url": url}
    final_slug = final_url.rstrip("/").split("/")[-1]
    if final_slug != slug:
        return [], {"source": "artificial_analysis", "model": model_name, "status": "redirect",
                    "error": f"重定向到 {final_url}（家族页/别名页），拒绝采用", "url": url}
    if len(body) < 5000 or "<title>404" in body or "not found" in body.lower()[:2000]:
        return [], {"source": "artificial_analysis", "model": model_name, "status": "not_found", "url": url}
    payloads = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', body, re.S)
    joined = "".join(p.encode().decode("unicode_escape", "ignore") for p in payloads)
    obs = []
    for key, metric in (("gpqa", "gpqa"), ("mmmuPro", "mmlu_pro")):
        m = re.search(r'"%s":([0-9.]+|null)' % key, joined)
        if m and m.group(1) != "null":
            v = float(m.group(1)) * 100
            if 0 <= v <= 100:
                obs.append({
                    "model_display": model_name, "metric": metric, "value": round(v, 2),
                    "source": "artificial_analysis", "source_type": SOURCE_TYPES["artificial_analysis"],
                    "source_url": url, "notes": f"Artificial Analysis 模型页 {slug}（RSC 数据）",
                })
    status = "ok" if obs else "no_benchmark_data"
    return obs, {"source": "artificial_analysis", "model": model_name, "status": status, "url": url}


# ---------------------------------------------------------------------------
# 适配器 2：OpenRouter Models API 的 Artificial Analysis 指数（辅助）
# ---------------------------------------------------------------------------
def fetch_openrouter_indices():
    """AA Intelligence/Coding/Agentic 指数。仅作辅助信号，不可顶替三项基准。"""
    body, err = fetch_body(OPENROUTER_MODELS_API)
    if body is None:
        return [], {"source": "openrouter_indices", "status": "unavailable", "error": err}
    try:
        data = json.loads(body).get("data", [])
    except ValueError:
        return [], {"source": "openrouter_indices", "status": "schema_changed", "error": "JSON 解析失败"}
    obs = []
    for m in data:
        bm = (m.get("benchmarks") or {}).get("artificial_analysis") or {}
        if not bm:
            continue
        for key, metric in (("intelligence_index", "aa_index_intelligence"),
                            ("coding_index", "aa_index_coding"),
                            ("agentic_index", "aa_index_agentic")):
            v = bm.get(key)
            if v is not None:
                obs.append({
                    "model_display": m.get("name") or m.get("id"),
                    "metric": metric, "value": round(float(v), 2),
                    "source": "openrouter_indices", "source_type": SOURCE_TYPES["openrouter_indices"],
                    "source_url": OPENROUTER_MODELS_API,
                    "notes": "OpenRouter 转发的 Artificial Analysis 指数（辅助信号，非 GPQA/SWE/MMLU 基准）",
                })
    return obs, {"source": "openrouter_indices", "status": "ok", "count": len(obs)}


def _openrouter_adapter(_models):
    return fetch_openrouter_indices()


ADAPTERS = {
    "artificial_analysis": lambda models, fresh=False: _batch(
        models, lambda m: fetch_artificial_analysis(m, fresh=fresh), source="artificial_analysis"),
    "openrouter_indices": lambda models, fresh=False: _openrouter_adapter(models),
}


def _batch(models, fn, source=None):
    """逐模型并发抓取（≤MAX_WORKERS 线程）；单模型异常隔离为 error 状态。"""
    obs, statuses = [], [None] * len(models)

    def _safe(m):
        try:
            o, st = fn(m)
            return o, st
        except Exception as e:
            return [], {"status": "error", "error": str(e)}

    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(models) or 1))) as ex:
        futures = {ex.submit(_safe, m): i for i, m in enumerate(models)}
        for fut in as_completed(futures):
            i = futures[fut]
            o, st = fut.result()
            obs.extend(o)
            statuses[i] = st
    return obs, {"source": source or fn.__name__, "status": "ok" if obs else "no_data",
                 "per_model": statuses}


def fetch_all(models, without=None, limit_per_source=None, fresh=False):
    """遍历适配器，返回 (observations, statuses)。失败隔离：单源异常不影响其他。

    fresh=True 时绕过页缓存强制抓取（用户明确要求最新评分）。
    """
    all_obs, statuses = [], []
    for name, adapter in ADAPTERS.items():
        if without and name in without:
            continue
        try:
            obs, st = adapter(models, fresh=fresh)
        except Exception as e:  # 适配器自身异常也必须隔离
            st = {"source": name, "status": "error", "error": str(e)}
            obs = []
        statuses.append(st)
        if limit_per_source and obs:
            obs = obs[:limit_per_source]
        all_obs.extend(obs)
    return all_obs, statuses


def main():
    ap = argparse.ArgumentParser(description="Benchmark 后备评分源")
    ap.add_argument("--models", default=None, help="逗号分隔的模型名；缺省为注册表全部模型")
    ap.add_argument("--without", default=None, help="逗号分隔的适配器名，跳过")
    ap.add_argument("--limit-per-source", type=int, default=None)
    ap.add_argument("--output", default="backup_scores.json")
    args = ap.parse_args()

    models = []
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from export_benchmark_excel import load_or_init_registry
        models = [m["name"] for m in load_or_init_registry()]
    without = set(args.without.split(",")) if args.without else set()

    obs, statuses = fetch_all(models, without=without, limit_per_source=args.limit_per_source)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {"fetched_at": now, "statuses": statuses, "observations": obs}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    for st in statuses:
        print(f"[{st['status']:<16}] {st['source']} {st.get('model', '')} {st.get('error', '')}")
    print(f"\n观测总数: {len(obs)}")
    for o in obs[:20]:
        print(f"  {o['model_display']:<32} {o['metric']:<24} {o['value']:<8} {o['source']}")
    if len(obs) > 20:
        print(f"  ... 等共 {len(obs)} 条")
    print(f"OUTPUT:{os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()