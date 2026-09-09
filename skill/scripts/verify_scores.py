# -*- coding: utf-8 -*-
"""Benchmark 分数自动核验脚本（verify_scores.py）。

对注册表中每个模型的每条分数，抓取声称来源页并做"模型名 + 指标 + 数值"三元组
匹配核验，结果写回注册表的 verification 字段，并在工作目录输出：
- score_verification_report.json  逐模型逐指标核验明细（含命中上下文摘录）
- verify_pending.json             需人工复核的队列（缺失 / 无法核验 / 数值不符）

取值规则（P0，防"参考值误当自身分"）：
- 只接受模型自身行的分数。页面上 "Best verified / best verified result / Versus
  best verified row" 属参考行，数值归属其他模型时必须排除；
- "Provider exact / 官方报告" 行优先；
- 无法抓取（403/WAF）、JS 渲染壳（SPA）、页面无数值 均标记为 unverified /
  missing，绝不猜测。

用法：
  python verify_scores.py                 # 核验注册表全部模型并写回
  python verify_scores.py --model "Kimi K3"   # 只核验指定模型
  python verify_scores.py --fresh         # 忽略本地页面缓存重新抓取
  python verify_scores.py --dry-run       # 只出报告，不写回注册表
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from discover_models import http_get
from export_benchmark_excel import DEFAULT_REGISTRY_PATH, load_or_init_registry, REQUIRED_METRICS, _atomic_json_dump
from skill_config import cache_enabled

CACHE_DIR = os.path.join(os.getcwd(), ".verify_cache")
CACHE_TTL = 86400
MAX_WORKERS = 6  # 并发上限（模型级并行），避免外部源限流时整体退化成串行慢速

METRIC_HINTS = {
    "gpqa": ["GPQA Diamond", "GPQA-D", "GPQA Graduate-Level", "GPQA", "GQA"],
    "swe_verified": ["SWE-bench Verified", "SWE-Bench Verified", "Software Engineering Benchmark", "SWE-bench"],
    "swe_pro": ["SWE-bench Pro", "SWE-Bench Pro", "SWE Pro"],
    "mmlu_pro": ["MMLU-Pro", "MMLU Pro", "Massive Multitask Language Understanding Prof", "MMLU"],
}

SOURCE_TYPE_BY_DOMAIN = {
    "openai.com": "official", "anthropic.com": "official", "z.ai": "official",
    "deepseek.com": "official", "huggingface.co": "official", "zhipuai.cn": "official",
    "gitee.com": "official", "swebench.com": "leaderboard", "scale.com": "leaderboard",
    "vals.ai": "aggregator", "benchlm.ai": "aggregator", "llm-stats.com": "aggregator",
    "requesty.ai": "aggregator", "artificialanalysis.ai": "aggregator",
}


def source_type(url):
    try:
        host = re.sub(r"^www\.", "", url.split("/")[2].lower())
    except Exception:
        return "unknown"
    for dom, st in SOURCE_TYPE_BY_DOMAIN.items():
        if host == dom or host.endswith("." + dom):
            return st
    return "unknown"


def norm(s):
    return re.sub(r"[\s\-_./:()（）]+", "", str(s)).lower()


def model_tokens(model):
    """返回足以确认模型身份的强匹配 token，不使用首个家族词。"""
    name = norm(model.get("name", ""))
    tokens = [name] if len(name) >= 6 else []
    model_id = str((model.get("discovered_via") or {}).get("model_id", ""))
    model_id = norm(model_id.split(":", 1)[0])
    if len(model_id) >= 6 and model_id not in tokens:
        tokens.append(model_id)
    return tokens


def fetch_body(url, fresh=False):
    """带磁盘缓存抓取；返回 (body, page_status)。每次抓取实时输出一行进度。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    path = os.path.join(CACHE_DIR, key + ".html")
    if not fresh and os.path.exists(path):
        try:
            if time.time() - os.path.getmtime(path) <= CACHE_TTL:
                print(f"  [fetch] 缓存命中 {url[:90]}", file=sys.stderr)
                with open(path, encoding="utf-8") as f:
                    return f.read(), "cached"
        except OSError:
            pass
    t0 = time.time()
    body, err = http_get(url, timeout=20, retries=2)
    if body is None:
        print(f"  [fetch] 失败({time.time() - t0:.1f}s) {url[:90]} -> {err}", file=sys.stderr)
        return "", f"unreachable:{err}"
    print(f"  [fetch] 完成({time.time() - t0:.1f}s) {url[:90]} ({len(body) // 1024}KB)", file=sys.stderr)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    except OSError:
        pass
    if len(body) < 3000 and re.search(r'<div id="root"></div>|__NEXT_DATA__|application/json', body):
        pass  # SPA 壳或数据壳，状态由 is_spa_shell 判定
    return body, "fetched"


def is_spa_shell(body):
    """JS 渲染壳：无正文但含框架/资源引用。"""
    if not body:
        return False
    text = re.sub(r"<script.*?</script>", " ", body, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text) < 120


def plain_text(body):
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<svg.*?</svg>", " ", body, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


def score_candidates(html, label):
    """多模式提取与 label 相关的分数候选。

    返回 [(value, region, context, labelled)]：
      region ∈ {"own","ref"}（ref 为 "Versus best verified row" 之后的参考行，一律排除）；
      labelled=True 表示上下文带指标标签可独立归属；False 仅在专属页兜底使用。
    """
    out = []
    text = plain_text(html)
    lowered = text.lower()
    lab = label.lower()

    for m in re.finditer(re.escape(lab), lowered):
        seg = text[m.start(): m.start() + 620]
        seg_low = seg.lower()
        mark = seg_low.find("versus best verified row")
        own_part = seg if mark == -1 else seg[:mark]
        ref_part = seg[mark:] if mark != -1 else ""
        sc = re.search(r"score\s*(\d+(?:\.\d+)?)\s*%", own_part, re.I)
        if sc:
            v = float(sc.group(1))
            if v <= 100:
                out.append((v, "own", own_part.strip()[:200], True))
        for n in re.findall(r"(\d+(?:\.\d+)?)\s*%", ref_part):
            v = float(n)
            if 0 <= v <= 100:
                out.append((v, "ref", ref_part.strip()[:120], True))
                break

    label_tok = label.replace("-", " ").split()[0].lower()
    label_norm = re.sub(r"[^a-z0-9]", "", label.lower())

    # aria-label（vals.ai / benchlm 风格）：分号前为自身行数字
    for ma in re.finditer(r'aria-label="([^"]*?\d+(?:\.\d+)?%[^"]*)"', html):
        attr = ma.group(1)
        attr_low = attr.lower()
        labelled = label_tok in attr_low or any(
            h.lower()[:6] in attr_low for h in METRIC_HINTS.get(label, []) if len(h) >= 6)
        parts = attr.split(";")
        nm = re.search(r"(\d+(?:\.\d+)?)\s*%", parts[0])
        if nm:
            v = float(nm.group(1))
            if v <= 100:
                out.append((v, "own", ("aria-label: " + parts[0]), labelled))

    # data-target 计数器（vals.ai 风格）：条形图在标签之后且 DOM 巨大，窗口放宽到 ±30KB
    for mt in re.finditer(r'data-target="(\d+(?:\.\d+)?)"', html):
        around = re.sub(r"[^a-z0-9]", "",
                        html[max(0, mt.start() - 30000): min(len(html), mt.end() + 30000)].lower())
        labelled = label_norm[:6] in around
        out.append((float(mt.group(1)), "own", "data-target counter", labelled))

    # JSON-LD PropertyValue（requesty.ai 风格）
    for mj in re.finditer(r'"name"\s*:\s*"Benchmark:\s*([^"]+)"\s*,\s*"value"\s*:\s*([\d.]+)', html):
        labelled = label.replace("_", "-").replace("-", " ").lower()[:8] in mj.group(1).lower()[:30]
        v = float(mj.group(2))
        if 0 <= v <= 100:
            out.append((v, "own", f"jsonld: Benchmark {mj.group(1)} value {v}", labelled))
    return out


def page_title(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return m.group(1).strip() if m else ""


def is_dedicated_page(html, tokens):
    """页面是否为该模型的专属页（title 含模型名）——此时无标签结构候选也可归属。"""
    t = norm(page_title(html))
    return bool(t) and any(tok in t for tok in tokens)


def verify_metric(model, key, claimed, url, body, page_status):
    """对单个 (model, key) 在单个来源页上核验。

    接受条件：
      - 数值必须来自 own 区域（"Versus best verified row" 之前的结构化行）；
      - 且该行上下文含本模型关键词，或页面为“模型专属页”（title 含模型名）；
      否则视为 unverifiable（页面未提及模型）或 missing（无自身数值）。
    """
    tokens = model_tokens(model)
    text = plain_text(body)
    page_has_model = any(t in norm(text) for t in tokens) if body else False

    if not body:
        return {"status": "unverifiable", "page_status": page_status, "reason": "页面不可获取"}
    if is_spa_shell(body):
        return {"status": "unverifiable", "page_status": "spa_shell", "reason": "JS 渲染壳，正文无法程序化提取"}

    dedicated = is_dedicated_page(body, tokens)
    label = REQUIRED_METRICS[key]
    candidates = score_candidates(html=body, label=label)
    # 只保留自己行；无标签结构候选仅在专属模型页兜底使用
    accepted = []
    for val, region, ctx, labelled in candidates:
        if region == "ref":
            continue
        if not labelled and not dedicated:
            continue
        ctx_norm = norm(ctx)
        owned = any(t in ctx_norm for t in tokens)
        if not (owned or dedicated):
            continue
        accepted.append((val, ctx))

    claimed_f = float(claimed)
    oks = [c for c in accepted if abs(c[0] - claimed_f) <= 0.05]
    if oks:
        best = min(oks, key=lambda c: abs(c[0] - claimed_f))
        best = ("ok", best[0], best[1])
    elif accepted:
        closest = min(accepted, key=lambda c: abs(c[0] - claimed_f))
        best = ("diff", closest[0], closest[1])
    else:
        best = None

    if best is None:
        if not page_has_model and not dedicated:
            return {"status": "unverifiable", "page_status": page_status,
                    "reason": "页面未提及该模型", "page_has_model": False, "claimed": float(claimed)}
        return {"status": "missing", "page_status": page_status,
                "reason": f"页面有 {label} 相关内容但未匹配到模型自身数值",
                "page_has_model": True, "claimed": float(claimed)}

    kind, val, ctx = best
    # 同页其他标签化观察值（排除计数器/参考行；体现"多来源冲突保留所有观察值"）
    alt_values = sorted({
        v for v, region, ctx2, lbl in candidates
        if region == "own" and lbl and ctx2 != "data-target counter" and abs(v - val) > 0.05
    })
    base = {
        "status": "ok" if kind == "ok" else "mismatch",
        "value": val,
        "claimed": float(claimed),
        "evidence": re.sub(r"\s+", " ", ctx)[:150],
        "page_status": page_status,
    }
    if alt_values:
        base["alt_values"] = alt_values
    return base


def metric_sources(model, key):
    """核验该指标要访问的 URL 列表（主页面 + 指标专属页）。"""
    urls = []
    if model.get("source_url"):
        urls.append(model["source_url"])
    mkey = {"gpqa": "gpqa_url", "swe_verified": "swe_url", "swe_pro": None, "mmlu_pro": "mmlu_url"}[key]
    if mkey and model.get(mkey) and model[mkey] != model.get("source_url"):
        urls.append(model[mkey])
    return urls


def verify_model(model, fresh=False):
    """核验一个模型全部指标，返回 {key: result}。"""
    results = {}
    body_cache = {}
    pages = {}
    for key in REQUIRED_METRICS:
        claimed = model.get(key)
        if claimed is None:
            results[key] = {"status": "missing", "reason": "注册表未录入该指标", "claimed": None}
            continue
        try:
            claimed_f = float(claimed)
        except (TypeError, ValueError):
            results[key] = {"status": "missing", "reason": "注册表分数不是数值", "claimed": claimed}
            continue
        if not 0 <= claimed_f <= 100:
            results[key] = {"status": "missing", "reason": "注册表分数超出 0-100 范围", "claimed": claimed}
            continue
        combined = []
        for url in metric_sources(model, key):
            if url not in body_cache:
                body_cache[url], page_status = fetch_body(url, fresh=fresh)
                pages[url] = page_status
            r = verify_metric(model, key, claimed, url, body_cache[url], pages[url])
            combined.append((url, r))
        if not combined:
            results[key] = {
                "status": "unverifiable",
                "reason": "注册表未提供可核验来源链接",
                "claimed": claimed_f,
            }
            continue
        ok = [(u, c) for u, c in combined if c["status"] == "ok"]
        mismatch = [(u, c) for u, c in combined if c["status"] == "mismatch"]
        if ok:
            best_u, best = min(ok, key=lambda uc: abs(uc[1]["value"] - claimed_f))
            results[key] = {**best, "status": "ok", "source_url": best_u}
        elif mismatch:
            mismatch_u, mismatch_r = mismatch[0]
            results[key] = {**mismatch_r, "source_url": mismatch_u or model.get("source_url")}
        else:
            best_u, best_r = max(combined, key=lambda uc: {"unverifiable": 2, "missing": 1, "ok": 0, "mismatch": 0}[uc[1]["status"]])
            results[key] = {**best_r, "source_url": best_u}
    return results


def write_back(model, results):
    metrics = {}
    statuses = []
    for key, r in results.items():
        claimed = model.get(key)
        entry = {
            "status": r["status"],
            "claimed": claimed,
            "source_url": r.get("source_url", model.get("source_url")),
            "source_type": source_type(r.get("source_url", model.get("source_url", ""))),
            "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if r.get("value") is not None:
            entry["verified_value"] = r["value"]
        reason = r.get("reason")
        if reason:
            entry["reason"] = reason
        if r.get("evidence"):
            entry["evidence"] = r["evidence"]
        metrics[key] = entry
        statuses.append(r["status"])
    overall = "verified" if all(s == "ok" for s in statuses) else (
        "mismatch" if any(s == "mismatch" for s in statuses) else "unverified")
    model["verification"] = {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": metrics,
    }
    return model


def apply_fallback(models, without=None, fresh=False):
    """从后备评分源（benchmark_sources.py）拉取观测，为未核验指标附上候选值。

    后备观测只作为人工复核候选写入 registry（verification.metrics[key].fallback），
    绝不自动升级为 ok；命中同时追加到 pending 队列（fallback_candidate）。
    fresh=True 时绕过页缓存强制抓取（用户明确要求最新评分）。
    返回 (observations, 命中数, 源状态列表)。
    """
    names = [m["name"] for m in models]
    try:
        from benchmark_sources import fetch_all as fetch_bs, names_match
    except ImportError:
        fetch_bs, names_match = None, None
    obs, statuses, hits, extra_pending = [], [], 0, []
    if fetch_bs:
        bs_obs, bs_statuses = fetch_bs(names, without=without, fresh=fresh)
        obs.extend(bs_obs)
        statuses.extend(bs_statuses)
    try:
        from render_sources import fetch_all as fetch_rs
    except ImportError:
        fetch_rs = None
    if fetch_rs:
        rs_obs, rs_statuses = fetch_rs(models=names)
        obs.extend(rs_obs)
        statuses.extend(rs_statuses)
    if names_match is None:
        return obs, 0, statuses, []
    for m in models:
        vm = (m.get("verification") or {}).get("metrics") or {}
        for key, r in vm.items():
            if r.get("status") == "ok":
                continue
            r.pop("fallback", None)  # 清除上一轮残留，按最新匹配规则重算
            cand = [o for o in obs if names_match(m["name"], o["model_display"])
                    and o["metric"] == key]
            if not cand:
                continue
            hits += 1
            r["fallback"] = {
                "source": cand[0]["source"], "value": cand[0]["value"],
                "source_type": cand[0]["source_type"], "source_url": cand[0]["source_url"],
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "notes": cand[0].get("notes", ""),
            }
            extra_pending.append({
                "model": m["name"], "metric": REQUIRED_METRICS.get(key, key),
                "claimed": r.get("claimed"), "status": "fallback_candidate",
                "source_url": cand[0]["source_url"],
                "reason": f"后备源 {cand[0]['source']} 提供候选值 {cand[0]['value']}，请人工确认后更新 claimed 并重跑核验",
            })
    return obs, hits, statuses, extra_pending


def main():
    ap = argparse.ArgumentParser(description="Benchmark 分数自动核验")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY_PATH)
    ap.add_argument("--model", default=None, help="只核验指定模型名称（显式指定时忽略缓存强制核验）")
    ap.add_argument("--company", default=None,
                    help="只核验指定公司/机构的模型（如 openai / deepseek / 智谱）")
    ap.add_argument("--fresh", action="store_true", help="忽略本地永久存储与页面缓存，全部重新核验")
    ap.add_argument("--dry-run", action="store_true", help="不写回注册表")
    ap.add_argument("--report", default="score_verification_report.json")
    ap.add_argument("--pending", default="verify_pending.json")
    ap.add_argument("--fallback", action="store_true",
                    help="核验后从后备评分源拉取候选值（人工复核用，不自动升级 ok）")
    ap.add_argument("--without", default=None, help="逗号分隔的后备源适配器名，跳过")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS,
                    help=f"模型级并发数（默认 {MAX_WORKERS}，上限 6）")
    args = ap.parse_args()

    registry = load_or_init_registry(args.registry)
    all_models = list(registry)
    if args.model:
        all_models = [m for m in all_models if m["name"] == args.model]
        if not all_models:
            print(f"ERROR: 未找到模型 {args.model}", file=sys.stderr)
            sys.exit(2)
    if args.company:
        from model_taxonomy import alias_matches, company_aliases, resolve_company_key
        key, _display = resolve_company_key(args.company)
        aliases = company_aliases(key) if key else []
        raw = str(args.company).strip().lower()
        all_models = [
            m for m in all_models
            if alias_matches(m.get("institution", ""), aliases or [raw])
        ]
        if not all_models:
            print(f"ERROR: 未找到公司/机构 {args.company} 对应的模型", file=sys.stderr)
            sys.exit(2)

    # 默认（缓存开启）：已有核验记录的模型直接复用本地永久存储结果，零联网；
    # 只对"没有核验记录的新模型"进行核验取分。--fresh / 显式 --model 时强制重验。
    use_cache = cache_enabled() and not args.fresh and not args.model
    models, cached_skipped = [], []
    for m in all_models:
        has_stored = bool(((m.get("verification") or {}).get("metrics") or {}))
        if use_cache and has_stored:
            cached_skipped.append(m)
        else:
            models.append(m)

    if cached_skipped:
        print(f"[cache] {len(cached_skipped)} 个模型复用本地永久存储的核验结果"
              f"（含评分与来源URL）；需要更新评分时加 --fresh 或提示语『更新最新AI模型评分』")
    if models:
        print(f"[待核验 {len(models)} 个] " + ", ".join(m["name"] for m in models))
    if not models:
        print("[cache] 全部模型均为缓存核验状态，本次零联网。")

    summary = {"ok": 0, "mismatch": 0, "missing": 0, "unverifiable": 0, "cached": len(cached_skipped)}
    report = {"checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "models": {}}
    pending = []
    for m in cached_skipped:
        vm = (m.get("verification") or {}).get("metrics") or {}
        report["models"][m["name"]] = {k: {**v, "cached": True} for k, v in vm.items()}
        # 缓存模型中的非 ok 项仍要进入人工复核队列，避免每次运行把队列清空
        for k, r in vm.items():
            if r.get("status") not in (None, "ok"):
                pending.append({
                    "model": m["name"], "metric": REQUIRED_METRICS.get(k, k),
                    "claimed": r.get("claimed"), "status": r.get("status"),
                    "source_url": r.get("source_url"),
                    "reason": r.get("reason") or r.get("evidence", "")[:120] or r.get("status"),
                    "cached": True,
                })
    t0 = time.time()
    if models:
        workers = max(1, min(args.workers, MAX_WORKERS, len(models)))
    else:
        workers = 1

    def _verify_one(m):
        """线程内完成抓取+判定+写回（各模型字典相互独立）；返回缓冲的输出行。"""
        lines = [f"== 核验 {m['name']} ({m['institution']})"]
        res = verify_model(m, fresh=args.fresh)
        write_back(m, res)
        counts = {"ok": 0, "mismatch": 0, "missing": 0, "unverifiable": 0}
        local_pending = []
        line = []
        for key in REQUIRED_METRICS:
            r = res[key]
            st = r["status"]
            v = r.get("verified_value", r.get("value"))
            reason = r.get("reason") or ""
            seg = f"  {key}={st}{f'({v})' if v is not None else ''}"
            if st in ("missing", "unverifiable") and reason:
                seg += f" [{reason}]"
            line.append(seg)
            if st != "ok":
                local_pending.append({
                    "model": m["name"], "metric": REQUIRED_METRICS[key],
                    "claimed": r.get("claimed"), "status": st,
                    "source_url": r.get("source_url"),
                    "reason": r.get("reason") or r.get("evidence", "")[:120] or st,
                })
            counts[st if st in counts else "unverifiable"] += 1
        lines.append(" |".join(line))
        lines.append(f"  overall: {m.get('verification', {}).get('status')}")
        return m["name"], res, lines, counts, local_pending

    # 模型级并行（≤6 线程）：抓取慢/限流源时整体耗时 ≈ 最慢一批，而非全部之和
    done, total, done_names = 0, len(models), set()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_verify_one, m): m for m in models}
        for fut in as_completed(futures):
            m = futures[fut]
            try:
                name, res, lines, counts, local_pending = fut.result()
            except Exception as e:
                print(f"== 核验 {m['name']} 线程异常: {e}", file=sys.stderr)
                name, res, lines = m["name"], {}, []
                counts = {"ok": 0, "mismatch": 0, "missing": 0, "unverifiable": 1}
                local_pending = []
            done += 1
            done_names.add(name)
            report["models"][name] = res
            for key, value in counts.items():
                summary[key] += value
            pending.extend(local_pending)
            print("\n".join(lines))
            remaining = [x["name"] for x in models if x["name"] not in done_names]
            rem_txt = ", ".join(remaining[:8]) + (f" 等{len(remaining)}个" if len(remaining) > 8 else "")
            print(f"[进度] 核验完成 {done}/{total}"
                  + (f"，剩余: {rem_txt}" if remaining else "（全部完成）"))
    print(f"\n核验阶段耗时: {time.time() - t0:.1f}s（{len(models)} 模型 x {workers} 并发）")

    fallback_hits = 0
    if args.fallback:
        cached_unresolved = [
            m for m in cached_skipped
            if any((r.get("status") or "missing") != "ok"
                   for r in ((m.get("verification") or {}).get("metrics") or {}).values())
        ]
        fallback_targets = models + cached_unresolved
        if not fallback_targets:
            print("[cache] 没有需要后备源补证的模型，跳过后备源拉取。")
        else:
            without = set(args.without.split(",")) if args.without else set()
            _obs, fallback_hits, src_statuses, extra_pending = apply_fallback(
                fallback_targets, without=without, fresh=args.fresh)
            pending.extend(extra_pending)
            for st in src_statuses:
                print(f"  [fallback:{st.get('status')}] {st.get('source')} {st.get('error', '')}")
    print(f"总耗时（含后备源）: {time.time() - t0:.1f}s")

    _atomic_json_dump(report, args.report)
    _atomic_json_dump(pending, args.pending)

    modified = 0
    if not args.dry_run:
        _atomic_json_dump(registry, args.registry)
        modified = len(models)

    print(f"\nSUMMARY: {json.dumps(summary, ensure_ascii=False)}")
    if args.fallback:
        print(f"FALLBACK_HITS:{fallback_hits}（后备源候选值，未自动升级 ok，见 verify_pending.json）")
    print(f"REPORT:{os.path.abspath(args.report)}")
    print(f"PENDING:{os.path.abspath(args.pending)}")
    print(f"REGISTRY_UPDATED:{modified} models")


if __name__ == "__main__":
    main()