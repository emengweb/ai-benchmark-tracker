# -*- coding: utf-8 -*-
"""渲染型后备评分源适配器（render_sources.py）。

对无稳定 JSON、需浏览器渲染的动态榜单页，通过 Playwright（无头 Chromium）
渲染后提取正文，按站点结构解析"模型名 + 指标 + 数值"行，输出与
benchmark_sources.py 同构的 Observation。

| 源 | URL | 解析指标 | 类型 |
| --- | --- | --- | --- |
| swebench | https://www.swebench.com/（CSS 网格表） | SWE-bench Verified（% RESOLVED，官方 Verified 榜单，含 agent 配置） | leaderboard |
| opencompass | https://rank.opencompass.org.cn/leaderboard/llm | 司南均分/知识/推理/数学/代码（中文综合维度，**辅助指标**） | leaderboard |
| scale_seal | https://labs.scale.com/leaderboard | 按区块标题映射：SWE→swe_verified / SWE Atlas→swe_pro / GPQA→gpqa / HLE→hle / FrontierMath→frontiermath；无法判定→aux_seal | leaderboard |

已实测移除：lmarena（https://lmarena.ai/leaderboard 重定向到 arena.ai 且渲染正文为空）。

依赖（可选，缺失时适配器报 unavailable 不影响其他源）：
  pip install playwright && playwright install chromium
或 Node 全局 playwright（自动回退 render_page.cjs）。

使用：
  python render_sources.py --sources swebench,opencompass
  python render_sources.py --models "Kimi K3,GPT-6 Astra" --output render_scores.json
"""
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RENDER_JS = os.path.join(SCRIPT_DIR, "render_page.cjs")
MAX_RENDER_WORKERS = 6  # 渲染源并发上限（每源独立浏览器/子进程，互不阻塞）

RENDER_SOURCES = {
    "swebench": {
        "url": "https://www.swebench.com/",
        "wait_ms": 12000,
        "parser": "swebench",
        "source_type": "leaderboard",
        "notes": "SWE-bench 官方 Verified 榜单（渲染后提取，分数含 agent 配置）",
    },
    "opencompass": {
        "url": "https://rank.opencompass.org.cn/leaderboard/llm",
        "wait_ms": 12000,
        "parser": "opencompass",
        "source_type": "leaderboard",
        "notes": "OpenCompass 司南 LLM 官方评测榜（渲染后提取，中文综合维度辅助指标）",
    },
    "scale_seal": {
        "url": "https://labs.scale.com/leaderboard",
        "wait_ms": 12000,
        "parser": "scale_seal",
        "source_type": "leaderboard",
        "notes": "Scale AI SEAL 盲测榜单（渲染后提取，按区块标题映射基准）",
    },
}

SEAL_METRIC_RULES = [
    (r"SWE Atlas|Refactoring", "swe_pro"),
    (r"SWE", "swe_verified"),
    (r"GPQA", "gpqa"),
    (r"Humanity", "hle"),
    (r"FrontierMath", "frontiermath"),
]


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def render_url(url, wait_ms=12000, selector=None, timeout=120):
    """渲染页面正文。优先 Python Playwright（同步 API），缺包时回退 Node 脚本。

    返回 (text, final_url, title, status)。
    """
    try:
        return _render_python(url, wait_ms, selector, timeout)
    except Exception as e:
        return "", url, "", f"python_render_error:{str(e)[:120]}"


def _render_python(url, wait_ms, selector, timeout):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _render_node(url, wait_ms, selector, timeout)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            if selector:
                try:
                    page.wait_for_selector(selector, timeout=20000)
                except Exception:
                    pass
            page.wait_for_timeout(wait_ms)
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
            title = page.title()
            return text, page.url, title, "ok"
        finally:
            browser.close()


def _render_node(url, wait_ms, selector, timeout):
    """回退：node render_page.cjs（需全局 playwright，NODE_PATH 注入）。"""
    env = dict(os.environ)
    try:
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=30)
        if npm_root.returncode == 0 and npm_root.stdout.strip():
            env["NODE_PATH"] = npm_root.stdout.strip()
    except Exception:
        pass
    cmd = ["node", RENDER_JS, url, str(wait_ms)]
    if selector:
        cmd.append(selector)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return "", url, "", "timeout"
    except FileNotFoundError:
        return "", url, "", "node_missing"
    out = (r.stdout or "").strip()
    if not out:
        return "", url, "", f"no_output({r.returncode})"
    try:
        data = json.loads(out)
    except ValueError:
        return "", url, "", "bad_json"
    if data.get("status") != "ok":
        return "", url, "", data.get("status", "error") + ":" + str(data.get("error", ""))[:120]
    return data.get("text", ""), data.get("finalUrl", url), data.get("title", ""), "ok"


# ---------------------------------------------------------------------------
# 站点解析器：输入渲染后的 innerText，输出 [{model, metric, value}]
# ---------------------------------------------------------------------------
def parse_swebench(text):
    """swebench.com：CSS 网格表，每单元格一行；排名行后跟模型名，再后跟纯数字得分。"""
    obs = []
    lines = [l.rstrip() for l in text.splitlines()]
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if re.match(r"^\d{1,3}$", ln) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and not re.match(r"^[\d.]+$", nxt) and not re.match(r"^(new|NEW|模型|MODEL)$", nxt):
                model = nxt
                for j in range(i + 2, min(i + 10, len(lines))):
                    sm = re.match(r"^(\d{1,3}(?:\.\d+)?)$", lines[j].strip())
                    if sm:
                        v = float(sm.group(1))
                        if 0 <= v <= 100:
                            obs.append({"model": model, "metric": "swe_verified", "value": round(v, 2)})
                        break
                i = j + 1 if 'sm' in dir() else i + 10
                continue
        i += 1
    return obs


def parse_opencompass(text):
    """司南 LLM 官方榜：模型名行 -> 机构行 -> '\t日期\t参数\t均分\t知识\t推理\t数学\t代码'。"""
    obs = []
    lines = [l.rstrip() for l in text.splitlines()]
    for i, ln in enumerate(lines):
        m = re.match(r"^\t(\d{4}/\d{1,2}/\d{1,2})\t[^\t]*\t([\d.]+)\t([\d.]+)\t([\d.]+)\t([\d.]+)\t([\d.]+)$", ln)
        if not m:
            continue
        if i < 2:
            continue
        org = lines[i - 1].strip()
        model = lines[i - 2].strip()
        if "·" not in org or not model:
            continue
        vals = [float(x) for x in m.groups()[1:]]
        for metric, v in zip(("ocp_avg", "ocp_knowledge", "ocp_reasoning", "ocp_math", "ocp_code"), vals):
            if 0 <= v <= 100:
                obs.append({"model": model, "metric": metric, "value": round(v, 2)})
    return obs


def parse_scale_seal(text):
    """SEAL 榜单：区块标题行 -> 排名行 -> 空 -> 模型行 -> 空 -> 'NN.NN±NN.NN' 分数行。"""
    obs = []
    lines = [l.rstrip() for l in text.splitlines()]
    current_block = ""
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln and re.match(r"^[\d.]+(?:±[\d.]+)?$", ln) and i >= 4:
            model_line = lines[i - 2].strip() if i >= 2 else ""
            rank_line = lines[i - 4].strip() if i >= 4 else ""
            if model_line and re.match(r"^\d{1,3}$", rank_line):
                v = float(re.match(r"^([\d.]+)", ln).group(1))
                metric = "aux_seal"
                low_block = current_block.lower()
                for pat, mkey in SEAL_METRIC_RULES:
                    if re.search(pat, low_block):
                        metric = mkey
                        break
                if 0 <= v <= 100:
                    obs.append({"model": model_line, "metric": metric, "value": round(v, 2)})
        elif ln and not ln.startswith("View") and len(ln) > 4 and "±" not in ln:
            # 候选区块标题：非导航词、含至少一个空格或基准关键字
            if any(k in ln for k in ("SWE", "Atlas", "GPQA", "Humanity", "FrontierMath", "Refactoring", "Bench", "Atlas")):
                current_block = ln
        i += 1
    return obs


PARSERS = {"swebench": parse_swebench, "opencompass": parse_opencompass, "scale_seal": parse_scale_seal}


def fetch_source(name, cfg, models):
    text, final_url, title, status = render_url(cfg["url"], cfg["wait_ms"])
    if status != "ok":
        return [], {"source": name, "status": status, "url": cfg["url"]}
    if len(text) < 200:
        return [], {"source": name, "status": "empty_page", "url": cfg["url"], "title": title}
    parser = PARSERS.get(cfg["parser"], lambda t: [])
    parsed = parser(text)
    obs = []
    for p in parsed:
        if models and not any(norm(p["model"]) == norm(m) or
                              (len(norm(m)) >= 6 and norm(m) in norm(p["model"]))
                              for m in models):
            continue
        obs.append({
            "model_display": p["model"], "metric": p["metric"], "value": p["value"],
            "source": name, "source_type": cfg["source_type"],
            "source_url": cfg["url"], "notes": cfg["notes"] + f"（{title[:40]}）",
        })
    return obs, {"source": name, "status": "ok" if obs else "no_model_rows", "url": cfg["url"]}


def fetch_all(models=None, sources=None):
    """并发遍历渲染源（≤MAX_RENDER_WORKERS）；单源失败不影响其他。"""
    all_obs, statuses = [], []
    names = [s for s in sources] if sources else list(RENDER_SOURCES)

    def _safe(name):
        cfg = RENDER_SOURCES.get(name)
        if not cfg:
            return [], {"source": name, "status": "unknown_source"}
        try:
            return fetch_source(name, cfg, models)
        except Exception as e:
            return [], {"source": name, "status": "error", "error": str(e)}

    with ThreadPoolExecutor(max_workers=max(1, min(MAX_RENDER_WORKERS, len(names) or 1))) as ex:
        futures = {ex.submit(_safe, name): name for name in names}
        for fut in as_completed(futures):
            obs, st = fut.result()
            statuses.append(st)
            all_obs.extend(obs)
    return all_obs, statuses


def main():
    ap = argparse.ArgumentParser(description="渲染型后备评分源")
    ap.add_argument("--sources", default=",".join(RENDER_SOURCES),
                    help=f"逗号分隔（可选 {list(RENDER_SOURCES)}）")
    ap.add_argument("--models", default=None, help="逗号分隔的模型名过滤")
    ap.add_argument("--output", default="render_scores.json")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",")] if args.models else None
    obs, statuses = fetch_all(models=models, sources=[s.strip() for s in args.sources.split(",") if s.strip()])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": now, "statuses": statuses, "observations": obs}, f, ensure_ascii=False, indent=2)

    for st in statuses:
        print(f"[{st['status']:<18}] {st['source']} {st.get('error', '')}")
    print(f"\n渲染源观测总数: {len(obs)}")
    for o in obs[:25]:
        print(f"  {o['model_display'][:40]:<40} {o['metric']:<16} {o['value']:<8} {o['source']}")
    print(f"OUTPUT:{os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()