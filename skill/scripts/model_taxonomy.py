# -*- coding: utf-8 -*-
"""Institution -> company / region taxonomy shared by the tracker scripts.

地域判定依据公司/机构信息：机构名小写化后做别名子串匹配，按规则顺序取第一个
命中的公司；无法识别时返回 "unknown"，绝不猜测。中英文别名与常见 OpenRouter
provider slug 一并收录，保证运行时发现的模型也能正确归类。
"""
import re

# (canonical_key, region, display, [aliases]) —— domestic 规则在前
INSTITUTION_RULES = [
    # ---- domestic（中国机构）----
    ("deepseek",  "domestic",      "深度求索 (DeepSeek)",        ["deepseek", "深度求索"]),
    ("alibaba",   "domestic",      "阿里云通义 (Alibaba Qwen)",  ["alibaba", "qwen", "阿里", "通义"]),
    ("zhipu",     "domestic",      "智谱 AI / Z.ai",             ["zhipu", "z.ai", "z-ai", "智谱", "glm"]),
    ("moonshot",  "domestic",      "月之暗面 (Moonshot AI)",     ["moonshotai", "moonshot", "月之暗面", "kimi"]),
    ("tencent",   "domestic",      "腾讯混元 (Tencent)",         ["tencent", "hunyuan", "腾讯", "混元"]),
    ("minimax",   "domestic",      "MiniMax",                    ["minimax"]),
    ("xiaomi",    "domestic",      "小米 AI (Xiaomi)",           ["xiaomi", "小米", "mimo"]),
    ("baidu",     "domestic",      "百度 (Baidu)",               ["baidu", "百度", "文心"]),
    ("bytedance", "domestic",      "字节跳动 (ByteDance)",       ["bytedance", "byteplus", "字节", "豆包", "doubao"]),
    ("stepfun",   "domestic",      "阶跃星辰 (StepFun)",         ["stepfun", "阶跃"]),
    ("01ai",      "domestic",      "零一万物 (01.AI)",           ["01.ai", "01ai", "零一万物", "lingyi"]),
    ("baichuan",  "domestic",      "百川智能 (Baichuan)",        ["baichuan", "百川"]),
    ("iflytek",   "domestic",      "讯飞星火 (iFlytek)",         ["iflytek", "讯飞"]),
    ("sensetime", "domestic",      "商汤 (SenseTime)",           ["sensetime", "商汤"]),
    ("inclusionai","domestic",     "InclusionAI (蚂蚁集团)",     ["inclusionai", "antling"]),
    # ---- international（海外机构）----
    ("openai",    "international", "OpenAI",                     ["openai"]),
    ("anthropic", "international", "Anthropic",                  ["anthropic", "claude"]),
    ("google",    "international", "Google",                     ["google", "deepmind", "gemini"]),
    ("nvidia",    "international", "NVIDIA",                     ["nvidia", "英伟达"]),
    ("meta",      "international", "Meta",                       ["meta", "facebook", "llama"]),
    ("mistral",   "international", "Mistral AI",                 ["mistral"]),
    ("xai",       "international", "xAI",                        ["x-ai", "xai", "grok"]),
    ("cohere",    "international", "Cohere",                     ["cohere"]),
    ("microsoft", "international", "Microsoft",                  ["microsoft", "微软"]),
    ("amazon",    "international", "Amazon",                     ["amazon", "aws"]),
    ("poolside",  "international", "Poolside",                   ["poolside"]),
    ("upstage",   "international", "Upstage",                    ["upstage"]),
    ("ibm",       "international", "IBM",                        ["ibm-granite", "ibm"]),
    ("inception", "international", "Inception Labs",             ["inception"]),
]

VALID_REGIONS = {"domestic", "international", "unknown"}

REGION_LABELS = {
    "all": "国内最新主流开源/商用模型 & 全球前沿旗舰模型",
    "domestic": "中国国产主流大模型（按机构所属地域自动筛选）",
    "international": "全球（中国以外）主流大模型（按机构所属地域自动筛选）",
}

# 用户/数据源可能写出的 region 同义词
REGION_SYNONYMS = {
    "domestic": "domestic", "cn": "domestic", "china": "domestic",
    "中国": "domestic", "国内": "domestic", "国产": "domestic",
    "international": "international", "global": "international", "overseas": "international",
    "国际": "international", "海外": "international", "国外": "international",
    "unknown": "unknown",
}


def classify_institution(institution):
    """返回 (region, canonical_key)；未识别 => ("unknown", None)。"""
    text = str(institution or "").strip().lower()
    if not text or re.search(r"\b(?:compatible|compatibility|api[- ]?compatible)\b", text):
        return "unknown", None
    for key, region, _display, aliases in INSTITUTION_RULES:
        for alias in aliases:
            alias = alias.lower()
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text):
                return region, key
    return "unknown", None


def resolve_company_key(company):
    """把用户输入的公司名解析为 (canonical_key|None, display|None)。

    canonical_key 为 None 时表示未命中规则表（调用方可退回原始子串匹配）。
    """
    text = str(company or "").strip().lower()
    if not text:
        return None, None
    if re.search(r"\b(?:compatible|compatibility|api[- ]?compatible)\b", text):
        return None, None
    for key, _region, display, aliases in INSTITUTION_RULES:
        if text == key or alias_matches(text, aliases):
            return key, display
    return None, None


def company_aliases(key):
    for k, _region, _display, aliases in INSTITUTION_RULES:
        if k == key:
            return [a.lower() for a in aliases]
    return []


def alias_matches(text, aliases):
    """按完整 provider/token 边界匹配别名，避免 meta 命中 metadata 等无关文本。"""
    value = str(text or "").strip().lower()
    for alias in aliases or []:
        alias = str(alias).strip().lower()
        if not alias:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", value):
            return True
        # 中文别名没有 ASCII token 边界，允许直接匹配中文机构名。
        if re.search(r"[\u4e00-\u9fff]", alias) and alias in value:
            return True
    return False


def institution_display(key, fallback=""):
    for k, _region, display, _aliases in INSTITUTION_RULES:
        if k == key:
            return display
    return fallback


def normalize_region(record):
    """补齐/校正单条记录的 region 字段（就地修改并返回）。

    显式合法的 region（含同义词）优先；缺失或无效时仅依据机构名推断，
    推断不出即为 "unknown"。
    """
    raw = str(record.get("region") or "").strip().lower()
    mapped = REGION_SYNONYMS.get(raw)
    if mapped in VALID_REGIONS:
        record["region"] = mapped
        return record
    region, _key = classify_institution(record.get("institution"))
    record["region"] = region
    return record


def normalize_records(records):
    return [normalize_region(dict(m)) for m in records]
