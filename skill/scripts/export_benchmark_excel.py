# -*- coding: utf-8 -*-
"""AI Benchmark Tracker 导出器：合并模型注册表 -> 按范围筛选 -> 加权排名 -> 生成 xlsx 天梯榜。

范围（scope）与公司（company）筛选必须在计分/排序/排名之前完成：
- scope=domestic / international / all（默认 all，保持旧行为）；
- company 追加公司级过滤（如 openai、deepseek、智谱），严禁筛选失败时回退到全量导出。

数据完整性与诚实性规则：
- 仅当 GPQA Diamond、SWE-bench Verified、MMLU-Pro 三项分数齐全且都在 [0,100] 时才计算
  加权综合得分并参与排名；缺项/无效的模型不参与综合排名，输出为“—”并标注缺失项；
- 绝不使用 SWE-bench Pro、Artificial Analysis 指数等代理指标顶替三项基准；
- 排序只发生在筛选后的集合内，排名从 1 重新编号。
"""
import os
import re
import sys
import json
import argparse
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from model_taxonomy import (
    resolve_company_key,
    company_aliases,
    normalize_records,
    REGION_LABELS,
)

DEFAULT_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models_registry.json")

# 18 Models for Phase 1 Baseline
DEFAULT_MODELS = [
    {
        "name": "GPT-6 Astra",
        "footnote_tag": "[1]",
        "institution": "OpenAI",
        "attribute": "前沿闭源",
        "multimodal": True,
        "release_date": "2026-09",
        "gpqa": 96.0,
        "swe_verified": 96.8,
        "swe_pro": 78.2,
        "mmlu_pro": 92.4,
        "price_input": 10.00,
        "price_output": 50.00,
        "notes": "当前顶尖科学发现与计算机操作（OSWorld 2.0: 72.6%）旗舰，突破 Critical 级网安边界",
        "source_url": "https://openai.com/index/gpt-6-astra/"
    },
    {
        "name": "Claude Opus 5",
        "footnote_tag": "[2]",
        "institution": "Anthropic",
        "attribute": "前沿闭源",
        "multimodal": True,
        "release_date": "2026-07",
        "gpqa": 95.8,
        "swe_verified": 96.5,
        "swe_pro": 77.0,
        "mmlu_pro": 91.8,
        "price_input": 15.00,
        "price_output": 75.00,
        "notes": "深度逻辑推演、生物医药分析及自适应思考标杆，具备极强的前瞻规划能力",
        "source_url": "https://www.anthropic.com/news/claude-opus-5"
    },
    {
        "name": "GPT-5.6 Sol",
        "footnote_tag": "[3]",
        "institution": "OpenAI",
        "attribute": "商用主力",
        "multimodal": True,
        "release_date": "2026-07",
        "gpqa": 94.6,
        "swe_verified": 96.2,
        "swe_pro": 64.6,
        "mmlu_pro": 90.1,
        "price_input": 2.00,
        "price_output": 10.00,
        "notes": "企业级复杂系统重构与深度分析中枢，支持 Cerebras Ultrafast 750 T/s 超高速推理",
        "source_url": "https://openai.com/index/previewing-gpt-5-6-sol/"
    },
    {
        "name": "Kimi K3",
        "footnote_tag": "[4]",
        "institution": "月之暗面",
        "attribute": "开源/商用",
        "multimodal": True,
        "release_date": "2026-07",
        "gpqa": 93.5,
        "gpqa_tag": "[4a]",
        "gpqa_url": "https://benchlm.ai/models/kimi-k3",
        "swe_verified": 93.4,
        "swe_tag": "[4b]",
        "swe_url": "https://www.vals.ai/models/kimi_kimi-k3",
        "swe_pro": 65.8,
        "mmlu_pro": 87.2,
        "mmlu_tag": "[4a]",
        "mmlu_url": "https://benchlm.ai/models/kimi-k3",
        "price_input": 0.80,
        "price_output": 3.20,
        "notes": "多模态深度长思考代表，前端工程与代码编写表现极其亮眼，Kimi Code Bench 榜首",
        "source_url": "https://www.vals.ai/models/kimi_kimi-k3"
    },
    {
        "name": "Claude Sonnet 5",
        "footnote_tag": "[5]",
        "institution": "Anthropic",
        "attribute": "企业主力",
        "multimodal": True,
        "release_date": "2026-06",
        "gpqa": 88.9,
        "swe_verified": 85.2,
        "swe_pro": 65.4,
        "mmlu_pro": 87.5,
        "price_input": 3.00,
        "price_output": 15.00,
        "notes": "兼顾前沿智力与极高执行稳定性的日常生产力首选，Terminal-Bench 得分领先",
        "source_url": "https://benchlm.ai/models/claude-sonnet-5"
    },
    {
        "name": "GLM-5.3",
        "footnote_tag": "[6]",
        "institution": "智谱 AI / Z.ai",
        "attribute": "开源权重",
        "multimodal": False,
        "release_date": "2026-08",
        "gpqa": 88.5,
        "swe_verified": 95.4,
        "swe_pro": 62.1,
        "mmlu_pro": 86.8,
        "price_input": 1.20,
        "price_output": 4.50,
        "notes": "753B MoE 显存优化架构，聚焦全栈编程与网络安全漏洞攻防（CyberGym 84.5%）",
        "source_url": "https://z.ai/blog/glm-5.3"
    },
    {
        "name": "DeepSeek V4 Pro",
        "footnote_tag": "[7]",
        "institution": "深度求索",
        "attribute": "全尺寸旗舰",
        "multimodal": False,
        "release_date": "2026-04",
        "gpqa": 91.2,
        "swe_verified": 88.6,
        "swe_pro": 63.4,
        "mmlu_pro": 88.0,
        "price_input": 0.80,
        "price_output": 2.40,
        "notes": "V4 完整参数旗舰版，多步自洽性与数理逻辑严密，复杂研究场景深度推演利器",
        "source_url": "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro"
    },
    {
        "name": "Hy4 preview",
        "footnote_tag": "[8]",
        "institution": "腾讯混元",
        "attribute": "开源/预览",
        "multimodal": True,
        "release_date": "2026-08",
        "gpqa": 92.3,
        "swe_verified": 85.4,
        "swe_pro": 55.4,
        "mmlu_pro": 86.5,
        "price_input": 0.00,
        "price_output": 0.00,
        "notes": "770B MoE (49B 激活)，长文本与泛工程调用爆发力强，具备极高并发吞吐能力",
        "source_url": "https://llm-stats.com/models/hy4-preview"
    },
    {
        "name": "GLM-5.3-Flash",
        "footnote_tag": "[9]",
        "institution": "智谱 AI / Z.ai",
        "attribute": "高吞吐 MoE",
        "multimodal": True,
        "release_date": "2026-08",
        "gpqa": 85.2,
        "swe_verified": 92.0,
        "swe_pro": 55.4,
        "mmlu_pro": 86.1,
        "price_input": 0.06,
        "price_output": 0.18,
        "notes": "320B MoE (18B 激活)，原生全模态支持，兼具低延迟与极低推理成本的高响应主力",
        "source_url": "https://z.ai/blog/glm-5.3-flash"
    },
    {
        "name": "Qwen 3.8 Max",
        "footnote_tag": "[10]",
        "institution": "阿里云通义",
        "attribute": "开源/商用",
        "multimodal": True,
        "release_date": "2026-08",
        "gpqa": 92.6,
        "swe_verified": 82.4,
        "swe_pro": 62.5,
        "mmlu_pro": 88.6,
        "price_input": 2.00,
        "price_output": 6.00,
        "notes": "2.4T 密集 MoE 超大底座，在国产模型中拥有最完整的长程自主 Agent 决策链",
        "source_url": "https://benchlm.ai/models/qwen3-8-max"
    },
    {
        "name": "MiniMax M3",
        "footnote_tag": "[11]",
        "institution": "MiniMax",
        "attribute": "全模态商用",
        "multimodal": True,
        "release_date": "2026-06",
        "gpqa": 92.9,
        "gpqa_tag": "[11a]",
        "gpqa_url": "https://www.requesty.ai/models/fireworks/minimax-m3",
        "swe_verified": 80.5,
        "swe_tag": "[11b]",
        "swe_url": "https://benchlm.ai/models/minimax-m3",
        "swe_pro": 58.2,
        "mmlu_pro": 84.2,
        "mmlu_tag": "[11b]",
        "mmlu_url": "https://benchlm.ai/models/minimax-m3",
        "price_input": 0.30,
        "price_output": 1.20,
        "notes": "512K/1M 混合全模态大模型，因优秀的高并发吞吐与免费策略在开发者生态中广受采纳",
        "source_url": "https://www.vals.ai/models/minimax_MiniMax-M3"
    },
    {
        "name": "DeepSeek V4 Flash",
        "footnote_tag": "[12]",
        "institution": "深度求索",
        "attribute": "高性价比 MoE",
        "multimodal": False,
        "release_date": "2026-07",
        "gpqa": 88.1,
        "swe_verified": 79.0,
        "swe_pro": 58.6,
        "mmlu_pro": 86.2,
        "price_input": 0.045,
        "price_output": 0.09,
        "notes": "284B MoE (13B 动态激活)，百万长文本与极低推理成本，全球开源高并发调用的首选基座",
        "source_url": "https://benchlm.ai/models/deepseek-v4-flash-0731"
    },
    {
        "name": "Gemini 3.7 Flash",
        "footnote_tag": "[13]",
        "institution": "Google",
        "attribute": "多模态主力",
        "multimodal": True,
        "release_date": "2026-05",
        "gpqa": 86.0,
        "swe_verified": 81.2,
        "swe_pro": 52.0,
        "mmlu_pro": 85.4,
        "price_input": 0.10,
        "price_output": 0.40,
        "notes": "结合 Google 百万上下文与高效搜索工具链，日常多模态与长篇文档速读表现稳健",
        "source_url": "https://llm-stats.com/models/gemini-3.7-flash"
    },
    {
        "name": "Nemotron 3 Ultra",
        "footnote_tag": "[14]",
        "institution": "NVIDIA",
        "attribute": "开源推理",
        "multimodal": False,
        "release_date": "2026-05",
        "gpqa": 84.5,
        "swe_verified": 78.6,
        "swe_pro": 51.0,
        "mmlu_pro": 83.5,
        "price_input": 0.20,
        "price_output": 0.20,
        "notes": "专为英伟达硬件端到端推理优化，在工具调用、结构化 JSON 输出上鲁棒性极佳",
        "source_url": "https://labs.scale.com/leaderboard"
    },
    {
        "name": "Laguna S 2.1",
        "footnote_tag": "[15]",
        "institution": "Poolside",
        "attribute": "专业代码",
        "multimodal": False,
        "release_date": "2026-05",
        "gpqa": 79.8,
        "swe_verified": 85.0,
        "swe_pro": 58.0,
        "mmlu_pro": 80.2,
        "price_input": 0.20,
        "price_output": 0.50,
        "notes": "专攻软件工程流水线定制的小型专业模型，专为 IDE 实时内联补全设计",
        "source_url": "https://benchlm.ai/coding"
    },
    {
        "name": "GPT-5.6 Luna",
        "footnote_tag": "[16]",
        "institution": "OpenAI",
        "attribute": "高并发轻量",
        "multimodal": True,
        "release_date": "2026-07",
        "gpqa": 82.4,
        "swe_verified": 74.5,
        "swe_pro": 48.2,
        "mmlu_pro": 82.0,
        "price_input": 0.15,
        "price_output": 0.60,
        "notes": "OpenAI 体系内高吞吐实时任务的性价比支柱，响应延迟极低且调用极其平稳",
        "source_url": "https://developers.openai.com/api/docs/models/gpt-5.6-luna"
    },
    {
        "name": "MiMo-V2.5",
        "footnote_tag": "[17]",
        "institution": "小米 AI",
        "attribute": "端云结合",
        "multimodal": True,
        "release_date": "2026-06",
        "gpqa": 81.2,
        "swe_verified": 72.0,
        "swe_pro": 46.5,
        "mmlu_pro": 81.6,
        "price_input": 0.10,
        "price_output": 0.30,
        "notes": "聚焦端侧协同、生活助理与快节奏多轮对话，中文语境下意图识别准确率优秀",
        "source_url": "https://llm-stats.com/"
    },
    {
        "name": "Solar Pro 4",
        "footnote_tag": "[18]",
        "institution": "Upstage",
        "attribute": "企业轻量",
        "multimodal": False,
        "release_date": "2026-06",
        "gpqa": 80.5,
        "swe_verified": 73.2,
        "swe_pro": 47.0,
        "mmlu_pro": 81.0,
        "price_input": 0.25,
        "price_output": 0.50,
        "notes": "深度微调轻量模型，在特定行业表格提取与严谨文档对齐上具备良好的落地表现",
        "source_url": "https://benchlm.ai/"
    }
]

# 每个脚注标签的来源描述（保留既有文案；新发现模型自动生成通用描述）
KNOWN_FOOTNOTE_DESC = {
    "[1]": "OpenAI官方发布及系统安全评测",
    "[2]": "Anthropic官方发布及BenchLM评测",
    "[3]": "OpenAI官方系统卡片及BenchLM评估",
    "[4a]": "BenchLM评测档案", "[4b]": "Vals AI实测验证报告",
    "[5]": "BenchLM及LLM Stats评测记录",
    "[6]": "智谱官方技术博客及BenchLM评测",
    "[7]": "官方HuggingFace模型卡片",
    "[8]": "腾讯混元官方发布及LLM Stats测评",
    "[9]": "智谱官方技术发布及Hugging Face数据",
    "[10]": "阿里通义官方文档及BenchLM评测",
    "[11a]": "Requesty基准实测", "[11b]": "Vals AI实测档案",
    "[12]": "BenchLM 0731版实测记录",
    "[13]": "LLM Stats 评测档案",
    "[14]": "Scale AI SEAL实验室盲测",
    "[15]": "BenchLM代码与软件工程专项评测",
    "[16]": "OpenAI官方开发者文档",
    "[17]": "小米AI技术报告及LLM Stats收录数据",
    "[18]": "Upstage官方发布及BenchLM评测数据",
}

REQUIRED_METRICS = {
    "gpqa": "GPQA Diamond",
    "swe_verified": "SWE-bench Verified",
    "mmlu_pro": "MMLU-Pro",
}

WEIGHTS = {"gpqa": 0.40, "swe_verified": 0.35, "mmlu_pro": 0.25}


def load_or_init_registry(registry_path=DEFAULT_REGISTRY_PATH):
    if os.path.exists(registry_path):
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                return normalize_records(raw)
        except Exception as e:
            print(f"WARNING: 读取注册表失败（{e}），将重新初始化", file=sys.stderr)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_MODELS, f, ensure_ascii=False, indent=2)
    return normalize_records(DEFAULT_MODELS)


def update_registry_with_new_models(new_models_list, registry_path=DEFAULT_REGISTRY_PATH):
    current = load_or_init_registry(registry_path)
    # 合并键：完整规范化模型名（不再是首词），避免同公司不同型号相互覆盖
    existing = {m["name"].strip().lower(): m for m in current}

    # 人工维护字段：同名更新时保留旧记录的值，防止 discover 元数据覆盖基线
    # 的 notes/source_url/脚注与指标链接（OpenRouter 目录页不含这些人工信息）
    protected = {"notes", "source_url", "footnote_tag", "gpqa_tag", "gpqa_url",
                 "swe_tag", "swe_url", "mmlu_tag", "mmlu_url", "attribute"}

    changed = False
    for nm in new_models_list:
        nm = normalize_records([dict(nm)])[0]
        key = nm["name"].strip().lower()
        if key in existing:
            old = existing[key]
            for k, v in nm.items():
                if v is None:
                    continue
                if k in protected and old.get(k):
                    continue  # 保留基线人工字段
                old[k] = v
            changed = True
        else:
            current.append(nm)
            existing[key] = nm
            changed = True

    if changed:
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    return current


def metric_value(m, key):
    """返回 [0,100] 范围内的数值分数；缺失/非数值/越界均视为无效 => None。"""
    if key not in m or m[key] is None:
        return None
    try:
        v = float(m[key])
    except (TypeError, ValueError):
        return None
    if not (0.0 <= v <= 100.0):
        return None
    return v


def metric_verification(m, key):
    """读取该指标的最新核验记录；无记录视为未核验（legacy）。"""
    vm = ((m.get("verification") or {}).get("metrics") or {}).get(key)
    if not vm:
        return {"status": "unverified", "claimed": m.get(key)}
    return vm


def metric_state(m, key):
    """综合核验记录与数值合法性，返回 {value, status, qualified}。

    status 语义（对应 verify_scores.py 输出 + legacy）：
      ok          已核验且数值一致 -> 可参与综合排名
      mismatch    来源值与声称值冲突（展示 verified_value，需人工复核）
      missing     来源页无值 / 注册表缺项
      unverified  未核验或无法核验（JS 渲染 / 被拦截 / 来源页未提及）
    只要任一指标不是 ok，该模型即不参与综合排名（诚实性原则）。
    """
    vm = metric_verification(m, key)
    st = vm.get("status", "unverified")
    claimed = metric_value(m, key)
    verified = metric_value(vm, "verified_value") if vm.get("verified_value") is not None else None

    if st == "ok":
        value = verified if verified is not None else claimed
        if value is None:
            st = "missing"
    elif st == "mismatch":
        value = verified
    elif st == "missing":
        value = None
    else:  # unverified / legacy
        value = claimed
        st = "unverified"
    return {"value": value, "status": st, "qualified": st == "ok"}


def prepare_models(models):
    """为每条记录补齐指标状态、缺失原因与综合得分（不修改传入记录）。

    资格规则：仅当 GPQA / SWE-bench Verified / MMLU-Pro 三项 metric_state 全部
    qualified（核验状态为 ok 且数值合法）才计算综合得分并参与排名；否则按原因
    标注（缺少 / 未核验 / 核验冲突），输出为“—”且不占排名。
    """
    prepared = []
    for m in models:
        p = dict(m)
        states = {k: metric_state(m, k) for k in REQUIRED_METRICS}
        reasons = []
        for k, label in REQUIRED_METRICS.items():
            st = states[k]
            if st["status"] == "missing":
                reasons.append(f"缺少 {label}")
            elif st["status"] == "mismatch":
                reasons.append(f"{label} 核验冲突（来源值与声称值不一致）")
            elif st["status"] == "unverified":
                reasons.append(f"{label} 未核验")
        p["_metric_states"] = states
        p["_missing"] = reasons
        if reasons:
            p["composite_score"] = None
        else:
            p["composite_score"] = round(
                sum(states[k]["value"] * w for k, w in WEIGHTS.items()), 2
            )
        prepared.append(p)
    return prepared


def filter_models(models, scope="all", company=None):
    """按地域与公司过滤；筛选结果为空时抛错，绝不回退全量。"""
    selected = list(models)
    if scope not in ("all", "domestic", "international"):
        raise ValueError(f"未知 scope: {scope}（可选 all/domestic/international）")

    if scope != "all":
        selected = [m for m in selected if m.get("region") == scope]

    if company:
        key, _display = resolve_company_key(company)
        if key:
            aliases = company_aliases(key)
            selected = [
                m for m in selected
                if aliases and any(a in str(m.get("institution", "")).lower() for a in aliases)
            ]
        else:
            raw = str(company).strip().lower()
            selected = [
                m for m in selected if raw in str(m.get("institution", "")).lower()
            ]

    if not selected:
        raise ValueError(
            f"筛选条件（scope={scope}, company={company or '无'}）下没有任何模型。"
            "请检查机构地域映射，或先运行 discover_models.py 发现模型。"
        )
    return selected


def scope_heading(scope, company_display=None):
    if company_display:
        qualifier = ""
        if scope == "domestic":
            qualifier = "（限国内）"
        elif scope == "international":
            qualifier = "（限国际）"
        return f"{company_display}{qualifier}模型"
    return {
        "all": "主流 AI 模型",
        "domestic": "国内主流 AI 模型",
        "international": "国际主流 AI 模型",
    }[scope]


def default_output_name(scope, company_display, timestamp_str):
    if company_display:
        safe = re.sub(r"[\s/()（）]+", "", company_display)
        base = f"2026{safe}模型综合能力与跑分天梯榜"
    elif scope == "domestic":
        base = "2026国内主流AI模型综合能力与跑分天梯榜"
    elif scope == "international":
        base = "2026国际主流AI模型综合能力与跑分天梯榜"
    else:
        base = "2026最新主流AI模型综合能力与跑分天梯榜"
    return f"{base}_{timestamp_str}.xlsx"


def build_footnotes(ordered_models):
    """从筛选后的模型记录动态派生底部溯源索引（去重、保留已知描述）。"""
    footnotes = []
    seen = set()
    for i, m in enumerate(ordered_models, 1):
        label = m.get("name", "?")
        main_tag = m.get("footnote_tag") or f"[{i}]"
        main_url = m.get("source_url", "")
        if main_url and main_tag not in seen:
            seen.add(main_tag)
            footnotes.append((
                main_tag, main_url,
                KNOWN_FOOTNOTE_DESC.get(main_tag) or f"{label} 评测数据来源（自动溯源）",
            ))
        for metric_key, tag_key, url_key in (
            ("GPQA", "gpqa_tag", "gpqa_url"),
            ("SWE-bench", "swe_tag", "swe_url"),
            ("MMLU-Pro", "mmlu_tag", "mmlu_url"),
        ):
            tag = m.get(tag_key)
            url = m.get(url_key)
            if not url:
                continue
            tag = tag or f"[{i}{metric_key[:1].lower()}]"
            if tag in seen:
                continue
            seen.add(tag)
            footnotes.append((tag, url, f"{label} {metric_key} 数据来源（自动溯源）"))
    return footnotes


def generate_excel(models_data=None, output_path=None, scope="all", company=None):
    if models_data is None:
        models_data = load_or_init_registry()

    models_data = normalize_records(models_data)
    company_display = resolve_company_key(company)[1] if company else None
    selected = filter_models(models_data, scope=scope, company=company)
    prepared = prepare_models(selected)

    ranked = [p for p in prepared if p["composite_score"] is not None]
    incomplete = [p for p in prepared if p["composite_score"] is None]
    ranked.sort(key=lambda x: x["composite_score"], reverse=True)
    incomplete.sort(key=lambda x: (len(x["_missing"]), x.get("name", "")))
    for idx, p in enumerate(ranked, 1):
        p["rank"] = idx
    for p in incomplete:
        p["rank"] = None
    ordered = ranked + incomplete

    now = datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    if output_path is None:
        output_path = default_output_name(scope, company_display, timestamp_str)

    heading = scope_heading(scope, company_display)
    if company:
        scope_label = f"{company_display or company} 旗下模型"
        if scope == "domestic":
            scope_label += "（限国内）"
        elif scope == "international":
            scope_label += "（限国际）"
    else:
        scope_label = REGION_LABELS[scope]

    wb = openpyxl.Workbook()
    ws1 = wb.active
    if company_display:
        ws1.title = f"{re.sub(r'[\s/()（）]+', '', company_display)}天梯榜"[:31]
    elif scope == "domestic":
        ws1.title = "国内AI模型综合天梯榜"
    elif scope == "international":
        ws1.title = "国际AI模型综合天梯榜"
    else:
        ws1.title = "主流AI模型综合天梯榜"

    font_title = Font(name="Microsoft YaHei", size=14, bold=True, color="1F4E79")
    font_subtitle = Font(name="Microsoft YaHei", size=9.5, italic=True, color="595959")
    font_header = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")

    font_model_name = Font(name="Microsoft YaHei", size=10, bold=True, color="000000")
    font_cell = Font(name="Microsoft YaHei", size=9.5, color="000000")
    font_bold_cell = Font(name="Microsoft YaHei", size=9.5, bold=True, color="000000")
    font_rank_top3 = Font(name="Microsoft YaHei", size=10, bold=True, color="C00000")
    font_muted = Font(name="Microsoft YaHei", size=9.5, italic=True, color="808080")
    font_warn = Font(name="Microsoft YaHei", size=9.5, italic=True, color="BF8F00")
    font_warn_bad = Font(name="Microsoft YaHei", size=9.5, italic=True, bold=True, color="C00000")

    font_subscript_link = Font(name="Microsoft YaHei", size=8, vertAlign="subscript", color="0563C1", underline="single")
    font_link_full = Font(name="Microsoft YaHei", size=9, color="0563C1", underline="single")
    font_fn_title = Font(name="Microsoft YaHei", size=10, bold=True, color="1F4E79")

    fill_header = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    fill_zebra = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
    fill_white = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    fill_top3 = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # Title Banner
    ws1.merge_cells("A1:N1")
    ws1["A1"] = f"2026 {heading}综合能力与 Benchmark 跑分评测天梯榜"
    ws1["A1"].font = font_title
    ws1["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws1.row_dimensions[1].height = 28

    ws1.merge_cells("A2:N2")
    incomplete_note = ""
    if incomplete:
        incomplete_note = f" | {len(incomplete)} 个模型 BenchMark 未完全核验或数据不完整，未参与综合排名（⚠=未核验/核验冲突）"
    ws1["A2"] = (
        f"跟踪范围：{scope_label} | 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"
        f"{incomplete_note} | 评分来源列放置于得分列后，仅数字带直链"
    )
    ws1["A2"].font = font_subtitle
    ws1["A2"].alignment = Alignment(horizontal="left", vertical="center")
    ws1.row_dimensions[2].height = 20

    headers = [
        "综合排名", "模型名称", "所属机构", "属性", "是否多模态", "发布年月",
        "加权综合得分", "评分来源", "GPQA Diamond (博士理科)", "SWE-bench Verified (代码工程)",
        "SWE-bench Pro", "MMLU-Pro (通识深度)", "参考定价 (输入/输出 $/M)", "核心特性与技术定位"
    ]

    ws1.append([])  # row 3 blank
    ws1.append(headers)  # row 4
    ws1.row_dimensions[4].height = 26

    for col_idx in range(1, len(headers) + 1):
        cell = ws1.cell(row=4, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = thin_border

    start_row = 5
    for row_offset, m in enumerate(ordered):
        curr_row = start_row + row_offset
        complete = m["composite_score"] is not None

        multimodal_raw = m.get("multimodal")
        multimodal_str = "✅ 是" if multimodal_raw is True else ("❌ 否" if multimodal_raw is False else "—")
        pi, po = m.get("price_input"), m.get("price_output")
        if pi is None or po is None:
            pricing_str = "待补充"
        elif float(pi) == 0 and float(po) == 0:
            pricing_str = "免费商用"
        else:
            pricing_str = f"${float(pi):.3f} / ${float(po):.2f}"

        model_name_clean = m["name"].split("[")[0].strip()
        fn_tag = m.get("footnote_tag") or (f"[{m['rank']}]" if m["rank"] else "")
        fn_formula = f'=HYPERLINK("{m["source_url"]}", "{fn_tag}")' if (m.get("source_url") and fn_tag) else "—"

        notes = m.get("notes") or ""
        if not complete:
            causes = "、".join(m["_missing"])
            notes = f"【未参与综合排名：{causes}】{notes}"

        g_state = m["_metric_states"]["gpqa"]
        s_state = m["_metric_states"]["swe_verified"]
        p_state = metric_state(m, "swe_pro")  # 仅展示，不计入综合
        l_state = m["_metric_states"]["mmlu_pro"]

        def cell_val(st):
            return st["value"] / 100.0 if st["value"] is not None else "—"

        row_data = [
            m["rank"] if complete else "—",
            model_name_clean,
            m.get("institution") or "未知机构",
            m.get("attribute") or "—",
            multimodal_str,
            m.get("release_date") or "—",
            m["composite_score"] if complete else "—",
            fn_formula,
            cell_val(g_state),
            cell_val(s_state),
            cell_val(p_state),
            cell_val(l_state),
            pricing_str,
            notes
        ]
        ws1.append(row_data)
        ws1.row_dimensions[curr_row].height = 23

        row_fill = fill_zebra if (row_offset % 2 == 1) else fill_white

        for col_idx in range(1, len(row_data) + 1):
            cell = ws1.cell(row=curr_row, column=col_idx)
            cell.border = thin_border
            cell.fill = row_fill
            cell.font = font_cell

            if col_idx == 1:  # Rank
                cell.alignment = align_center
                cell.font = font_rank_top3 if complete and m["rank"] <= 3 else (font_bold_cell if complete else font_muted)
            elif col_idx == 2:  # Model Name - STRICTLY PLAIN TEXT BOLD, NO HYPERLINK!
                cell.alignment = align_left
                cell.font = font_model_name
            elif col_idx in [3, 4]:  # Institution, Attribute
                cell.alignment = align_left
            elif col_idx in [5, 6]:  # Multimodal, Date
                cell.alignment = align_center
            elif col_idx == 7:  # Composite Score
                cell.alignment = align_right
                if complete:
                    cell.font = font_bold_cell
                    cell.number_format = '0.00'
                    if m["rank"] <= 3:
                        cell.fill = fill_top3
                else:
                    cell.font = font_muted
            elif col_idx == 8:  # 评分来源
                cell.alignment = align_center
                cell.font = font_subscript_link if fn_tag else font_muted
            elif col_idx == 9:  # GPQA
                cell.alignment = align_right
                st = g_state
                if isinstance(row_data[8], str):
                    cell.font = font_muted
                elif st["status"] == "ok":
                    cell.number_format = '0.0%'
                    if "gpqa_url" in m:
                        cell.value = f'=HYPERLINK("{m["gpqa_url"]}", "{st["value"]:.1f}% {m.get("gpqa_tag", "")}")'
                        cell.font = font_subscript_link
                elif st["status"] == "mismatch":
                    cell.number_format = '0.0%"⚠"'
                    cell.font = font_warn_bad
                else:
                    cell.number_format = '0.0%"⚠"'
                    cell.font = font_warn
            elif col_idx == 10:  # SWE-bench Verified
                cell.alignment = align_right
                st = s_state
                if isinstance(row_data[9], str):
                    cell.font = font_muted
                elif st["status"] == "ok":
                    cell.number_format = '0.0%'
                    if "swe_url" in m:
                        cell.value = f'=HYPERLINK("{m["swe_url"]}", "{st["value"]:.1f}% {m.get("swe_tag", "")}")'
                        cell.font = font_subscript_link
                elif st["status"] == "mismatch":
                    cell.number_format = '0.0%"⚠"'
                    cell.font = font_warn_bad
                else:
                    cell.number_format = '0.0%"⚠"'
                    cell.font = font_warn
            elif col_idx == 11:  # SWE-bench Pro（仅展示）
                cell.alignment = align_right
                st = p_state
                if isinstance(row_data[10], str):
                    cell.font = font_muted
                elif st["status"] == "mismatch":
                    cell.number_format = '0.0%"⚠"'
                    cell.font = font_warn_bad
                elif st["status"] == "ok":
                    cell.number_format = '0.0%'
                else:
                    cell.number_format = '0.0%'
                    cell.font = font_muted
            elif col_idx == 12:  # MMLU-Pro
                cell.alignment = align_right
                st = l_state
                if isinstance(row_data[11], str):
                    cell.font = font_muted
                elif st["status"] == "ok":
                    cell.number_format = '0.0%'
                    if "mmlu_url" in m:
                        cell.value = f'=HYPERLINK("{m["mmlu_url"]}", "{st["value"]:.1f}% {m.get("mmlu_tag", "")}")'
                        cell.font = font_subscript_link
                elif st["status"] == "mismatch":
                    cell.number_format = '0.0%"⚠"'
                    cell.font = font_warn_bad
                else:
                    cell.number_format = '0.0%"⚠"'
                    cell.font = font_warn
            elif col_idx == 13:  # Pricing
                cell.alignment = align_center
            elif col_idx == 14:  # Notes
                cell.alignment = align_left

    # Footnote Section at Bottom（动态派生，仅包含当前筛选结果的数据源）
    fn_start = start_row + len(ordered) + 1
    ws1.cell(row=fn_start, column=1, value="【跑分数据来源与精准溯源索引（点击数字直达来源页）】").font = font_fn_title

    footnotes = build_footnotes(ordered)
    for idx, (tag, url, desc) in enumerate(footnotes, 1):
        cell_fn = ws1.cell(row=fn_start + idx, column=1)
        cell_fn.value = f'=HYPERLINK("{url}", "{tag} {desc} -> {url}")'
        cell_fn.font = font_link_full

    col_widths = {
        1: 10, 2: 22, 3: 16, 4: 14, 5: 12, 6: 12, 7: 14, 8: 12,
        9: 24, 10: 26, 11: 15, 12: 20, 13: 20, 14: 55
    }
    for col_idx, width in col_widths.items():
        ws1.column_dimensions[get_column_letter(col_idx)].width = width

    # Sheet 2: Benchmarks Reference
    ws2 = wb.create_sheet(title="评测基准说明")
    ws2.append(["评测基准 (Benchmark)", "中文官方名称", "主要考察能力维度", "行业代表性与核心意义"])
    ws2.row_dimensions[1].height = 25
    for col_idx in range(1, 5):
        cell = ws2.cell(row=1, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center

    benchmarks = [
        ("GPQA Diamond", "博士级科学推理基准", "物理、化学、生物等高阶学科推理", "前沿模型科学推理能力的关键标尺，权重 40%"),
        ("SWE-bench Verified", "真实代码工程任务基准", "从 GitHub 真实 issue 修复到测试通过", "衡量模型真实软件工程落地能力，权重 35%"),
        ("SWE-bench Pro", "进阶代码工程任务基准", "更复杂的跨文件大型工程修复任务", "工程能力进阶参考，不计入综合得分"),
        ("MMLU-Pro", "多学科知识理解基准", "广泛学科专业知识与推理", "衡量模型通识知识的广度与深度，权重 25%"),
    ]
    for row_idx, b in enumerate(benchmarks, 2):
        ws2.append(list(b))
        ws2.row_dimensions[row_idx].height = 22
        for col_idx in range(1, 5):
            c = ws2.cell(row=row_idx, column=col_idx)
            c.border = thin_border
            c.font = font_cell
            c.alignment = align_left if col_idx > 1 else align_center
    ws2.append([])
    ws2.append(["综合得分公式", "GPQA Diamond × 0.40 + SWE-bench Verified × 0.35 + MMLU-Pro × 0.25", "", "仅三项分数均核验通过（ok）且完整时参与综合排名；未核验/核验冲突/缺项模型不占排名"])
    for col_idx in range(1, 5):
        c = ws2.cell(row=ws2.max_row, column=col_idx)
        c.font = font_bold_cell

    ws2.column_dimensions['A'].width = 22
    ws2.column_dimensions['B'].width = 30
    ws2.column_dimensions['C'].width = 45
    ws2.column_dimensions['D'].width = 45

    # Sheet 3: Direct Sources
    ws3 = wb.create_sheet(title="数据源清单")
    ws3.append(["维度", "数据平台 / 机构", "直接访问网址 (Deep Link)", "提取与监测指标"])
    ws3.row_dimensions[1].height = 25
    for col_idx in range(1, 5):
        cell = ws3.cell(row=1, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center

    sources = [
        ("模型目录", "OpenRouter Models API", "https://openrouter.ai/api/v1/models", "模型 id/名称/上下文/多模态/定价/发布时间"),
        ("工程落地", "SWE-bench (普林斯顿官方)", "https://www.swebench.com/", "SWE-bench Verified, SWE-bench Pro"),
        ("综合质量与成本", "Artificial Analysis", "https://artificialanalysis.ai/", "Intelligence Index, TTFT, Tokens/s, 价格"),
        ("学术推理盲测", "Scale AI SEAL Labs", "https://labs.scale.com/leaderboard", "GPQA Diamond, Humanity's Last Exam"),
        ("前沿数学极限", "Epoch AI", "https://epoch.ai/frontiermath", "FrontierMath 各阶梯得分"),
        ("动态防污染", "LiveBench", "https://livebench.ai/", "LiveCodeBench, 动态多维度打分"),
        ("盲测对战", "LMSYS Chatbot Arena", "https://huggingface.co/spaces/lmarena-ai/arena-leaderboard", "Arena Elo 积分, Arena-Hard 胜率"),
        ("国内学术基准", "OpenCompass 司南", "https://rank.opencompass.org.cn/", "C-Eval, CMMLU, 中文长文本原子能力"),
    ]
    for row_idx, s in enumerate(sources, 2):
        ws3.append(list(s))
        ws3.row_dimensions[row_idx].height = 22
        for col_idx in range(1, 5):
            c = ws3.cell(row=row_idx, column=col_idx)
            c.border = thin_border
            c.font = font_cell
            c.alignment = align_left if col_idx > 2 else align_center

    ws3.column_dimensions['A'].width = 18
    ws3.column_dimensions['B'].width = 25
    ws3.column_dimensions['C'].width = 45
    ws3.column_dimensions['D'].width = 35

    wb.save(output_path)
    print(f"OUTPUT_PATH:{output_path}")
    print(f"MODELS_INCLUDED:{len(ordered)} (ranked={len(ranked)}, incomplete={len(incomplete)})")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Benchmark 天梯榜导出器")
    parser.add_argument("--add-model", type=str, help="JSON string representing a new model to add or update")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--scope", type=str, default="all",
                        choices=["all", "domestic", "international"],
                        help="地域范围：all=国内外全部（默认）/ domestic=仅国内 / international=仅国际")
    parser.add_argument("--company", type=str, default=None,
                        help="公司/机构过滤，如 openai / deepseek / 智谱；与 --scope 可叠加")
    args = parser.parse_args()

    if args.add_model:
        try:
            m_obj = json.loads(args.add_model)
            update_registry_with_new_models([m_obj])
            print(f"Added/updated model: {m_obj.get('name')}")
        except Exception as e:
            print(f"Error parsing model JSON: {e}", file=sys.stderr)

    try:
        generate_excel(output_path=args.output, scope=args.scope, company=args.company)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception:
        raise