---
name: ai-benchmark-tracker
description: Continuously track, discover, fetch, extract, analyze, and aggregate latest AI model benchmark evaluation data, and export to a structured Excel spreadsheet (.xlsx) with timestamp suffix uploaded to Google Drive. Use when the user asks to monitor, track, refresh, discover new models, or export AI model benchmarks, leaderboard rankings, or create benchmark Excel reports for domestic and global models. 自动识别用户要求的范围（国内/国产、国际/海外，或指定公司如 OpenAI、DeepSeek），运行时通过 OpenRouter 目录发现最新模型、采集可核验的 Benchmark 评分，加权计算综合得分并排名，生成带时间戳的 Excel（.xlsx）天梯榜并可上传 Google Drive。当用户要求整理、追踪、刷新最新 AI 模型跑分或评测数据，发现新发布模型，生成、更新或导出国内外大模型综合能力天梯榜、跑分排行榜、Benchmark Excel 报告时使用。
---

Automated pipeline for tracking, runtime discovery, and benchmark data aggregation across domestic and international AI models. Computes mathematical composite rankings, attaches deep-link traceability, and generates timestamped Excel workbooks (.xlsx) uploaded to Google Drive.

## 中文说明与调用范例

本技能持续追踪、抓取并汇总国内外最新 AI 大模型的 Benchmark 评测数据（GPQA Diamond、SWE-bench Verified / SWE-bench Pro、MMLU-Pro、参考定价等），按固定权重（GPQA 40% + SWE-bench Verified 35% + MMLU-Pro 25%）计算加权综合得分并降序排名，最终生成带时间戳后缀的 Excel（.xlsx）天梯榜文档，可上传至 Google Drive 交付。

**范围识别**：先按用户措辞解析目标范围（国内 / 国际 / 指定公司 / 全部），再执行“运行时发现模型 → 采集评分证据 → 按范围导出”。模型清单是变化的：默认发现最新/热门模型（OpenRouter 月榜前 20 左右），用户指定地域或公司时只发现并汇总该范围的模型。

中文调用范例（用户说以下类似的话时，应触发本技能）：

- “整理国内最新 AI 模型 benchmark，汇总成 xlsx 天梯榜” → 仅国内模型
- “刷新一下国内外主流大模型的跑分数据，生成新的 Excel 报告” → 全部
- “整理 OpenAI 公司的 AI 模型评分，汇总成 xlsx” → 仅 OpenAI
- “看看最近有哪些新模型发布，把它们的评测分数合并进榜单”
- “更新模型天梯榜并上传到 Google Drive”

## Core Mandate: Deliverable Format

- **Format**: All deliverables MUST be structured Excel workbooks (`.xlsx`). NEVER deliver Word documents or Google Docs unless explicitly requested.
- **Timestamped Filenames**: Every generated Excel file MUST append a date-time suffix formatted as `YYYYMMDD_HHMMSS` (e.g. `2026国内主流AI模型综合能力与跑分天梯榜_20260908_092612.xlsx`) to avoid overwriting and enable versioned tracking.
- **Output Location**: Without `--output`, the workbook is generated in the **current working directory**, not a fixed directory.

## 范围识别规则（Scope Resolution → 不可回退）

1. 用户提到 `国内` / `国产` / `中国` / 中文厂商 → `--scope domestic`，只允许中国的机构（深度求索、智谱、月之暗面、腾讯混元、阿里云通义、MiniMax、小米、百度、字节、阶跃、零一、百川、讯飞、商汤等）。
2. 用户提到 `国际` / `海外` / `国外` / 海外厂商 → `--scope international`。
3. 用户指定具体公司（OpenAI / Anthropic / DeepSeek / 智谱 / 月之暗面 / 腾讯 / 阿里 / 小米……）→ 追加 `--company <名称或别名>`，可与 `--scope` 叠加。
4. `国内外` / `全球` / `最新` / 未限定范围 → `--scope all`（默认）。
5. **铁律**：用户限定了范围，就绝不能把默认的 18 模型全量清单塞进交付物；筛选结果为空时脚本会报错，此时应扩大发现范围（运行 discover 补录）而不是回退到全量导出。
6. 地域判定依据公司/机构信息（含中英文别名与 OpenRouter provider slug），规则表见 `scripts/model_taxonomy.py`；无法识别的机构标为 unknown，不会进入国内/国际范围。

## When to Use

- Tracking or refreshing latest benchmark evaluation data for mainstream domestic or international AI models, or for models of a specific company.
- Dynamically discovering newly released models and retrieving their benchmark scores at runtime (default: latest/hot models, e.g. OpenRouter monthly top ~20).
- Generating, updating, or exporting structured benchmark Excel reports (.xlsx) with Google Drive shareable links.
- Enforcing strict column order ("评分来源" immediately following "加权综合得分"), plus granular deep-link footnote traceability with subscript hyperlinks.

## Target Models (Phase 1 Baseline)

内置基线仅作无网络时的兜底参考；正常流程以运行时发现为准。

1. Domestic Mainstream Open-Source and Commercial Models:
   - DeepSeek: DeepSeek V4 Pro, DeepSeek V4 Flash
   - Alibaba: Qwen 3.8 Max, QwQ series
   - Zhipu AI (Z.ai): GLM-5.3, GLM-5.3-Flash
   - Moonshot AI: Kimi K3, Kimi k1.5
   - Tencent: Hy4 preview, Hy3
   - MiniMax: MiniMax M3
   - Xiaomi: MiMo-V2.5

2. Global Top 20 Frontier Flagships:
   - OpenAI: GPT-6 Astra, GPT-5.6 Sol, GPT-5.6 Luna, o1, o3-mini
   - Anthropic: Claude Opus 5, Claude Sonnet 5, Claude 3.7 Sonnet
   - Google: Gemini 3.7 Flash, Gemini 2.0 Pro
   - NVIDIA: Nemotron 3 Ultra
   - Poolside: Laguna S 2.1
   - Upstage: Solar Pro 4

## Table Structure and Column Sequence Rules

The Excel sheet columns MUST strictly follow this exact order:
1. `综合排名` (Rank)
2. `模型名称` (Model Name: Plain text bold black, strictly unlinked)
3. `所属机构` (Institution: Split column)
4. `属性` (Attribute / Model Tier: Split column)
5. `是否多模态` (Multimodal: `✅ 是` / `❌ 否`)
6. `发布年月` (Release Date: `YYYY-MM`)
7. `加权综合得分` (Weighted Composite Score: Rounded to 2 decimals)
8. `评分来源` (Score Source: Placed immediately after Weighted Score; uses subscript 8pt font with direct hyperlink formula `=HYPERLINK(url, "[xx]")`)
9. `GPQA Diamond (博士理科)`
10. `SWE-bench Verified (代码工程)`
11. `SWE-bench Pro`
12. `MMLU-Pro (通识深度)`
13. `参考定价 (输入/输出 $/M)`
14. `核心特性与技术定位`

## Footnote Traceability Rules (Data Closure)

1. Hyperlink Target:
   - The hyperlink MUST ONLY be applied to the `[xx]` or `xx` number inside the "评分来源" column (or specific benchmark cells for multi-source models). The model name itself MUST remain unlinked plain text.
2. Subscript Styling:
   - Footnotes must use smaller subscript formatting (8pt, `vertAlign='subscript'`).
3. Multi-source Models:
   - If a model's benchmarks originate from different independent platforms (e.g. Kimi K3, MiniMax M3), attach distinct subscript footnote links (e.g. `93.5% [4a]`, `93.4% [4b]`) directly inside each respective score cell.
4. Direct Deep Links:
   - All URLs must point specifically to the model evaluation page, not generic homepages.
5. Scope Consistency:
   - The bottom of Sheet 1 lists the deep-link footnote index **derived dynamically from the selected models only** — a domestic report never contains international source entries (the script enforces this).

## Data Completeness & Honesty Rules

- 综合得分仅在 GPQA Diamond、SWE-bench Verified、MMLU-Pro **三项分数都齐全且有效**时才计算；任何缺项模型在表格中显示 `—`，明确标注“数据不完整，未参与综合排名”，排名从 1 只覆盖完整记录。
- **禁止**用 SWE-bench Pro、Artificial Analysis Intelligence/Coding Index、Arena Elo 等代理指标顶替或换算这三个基准分。
- 分数必须有可核验来源（官方系统卡/基准官方结果页/可复现评测），并记录来源 URL；同一模型多来源冲突时保留所有观察值，按“基准官方 > 厂商系统卡 > 独立评测 > 聚合站”优先级取用，绝不平均。
- 网络/动态页面不可获取时，如实报告 `unavailable_dynamic_source` / 缓存降级状态，不编造数据。

## Dynamic Runtime Model Discovery Workflow

### Stage A: 运行时发现模型（目录 API，非静态清单）

以 OpenRouter 公开模型目录为主源（https://openrouter.ai/api/v1/models，公开 JSON），必要时用月榜页（https://openrouter.ai/rankings?view=month）作热度排序启发。执行本地脚本：

```bash
# 默认：最新/热门模型（--use-rankings 时尝试月榜顺序启发，失败自动回退最新发布优先）
python <skill_dir>/scripts/discover_models.py --scope all --use-rankings --limit 20

# 按地域：国内 / 国际
python <skill_dir>/scripts/discover_models.py --scope domestic --limit 20
python <skill_dir>/scripts/discover_models.py --scope international --limit 20

# 按公司：公司名可用中文或英文/别名（openai / deepseek / 智谱 / 月之暗面 ...）
python <skill_dir>/scripts/discover_models.py --company openai --limit 20
```

- `<skill_dir>` is this skill's installed directory (e.g. `~/.zcode/skills/ai-benchmark-tracker`); resolve the actual path at runtime.
- Use `python` on Windows, `python3` on Linux/macOS — check availability if the first attempt fails.
- 输出为 JSON（`summary` + `models`），每条记录含：name、institution、region、multimodal、release_date、price_input/output（$/1M）、source_url（OpenRouter 模型页）、discovered_via（来源/获取时间）。**不含伪造分数**。
- 网络失败自动回退本地缓存 `openrouter_models_cache.json` 并标注 stale；无缓存则报错退出。

### Stage B: 逐模型采集 Benchmark 证据

对 Stage A 选出的每个模型（数量有限，逐模型处理），用 `google:search` 搜索其官方系统卡与基准结果页：

- 查询词：`"<模型名>" "GPQA Diamond" "SWE-bench Verified" "MMLU-Pro" pricing`；国内模型另查 OpenCompass 司南与厂商技术博客。
- 提取字段：GPQA Diamond %、SWE-bench Verified %、SWE-bench Pro %、MMLU-Pro %、输入/输出定价（$/M token）、发布年月、核心定位、以及**每条分数对应的来源直链**。
- 记录分数来源类型与获取时间；无法核验的分数**留空**（不要臆造），进入导出时即为“数据不完整”状态。
- 权威 Benchmark 数据集（SWE-bench、MMLU-Pro 的 Hugging Face 数据）不是实时成绩接口，不能用下载数据集代替模型得分。

### Stage C: 补录新模型并按范围导出 Excel

```bash
# 补录一条新发现的模型（region 可省略：脚本按机构自动归类；分数未采集到时省略对应字段）
python <skill_dir>/scripts/export_benchmark_excel.py --add-model '{"name": "模型名", "institution": "机构", "attribute": "属性", "multimodal": true, "release_date": "2026-09", "gpqa": 90.0, "swe_verified": 85.0, "swe_pro": 60.0, "mmlu_pro": 88.0, "price_input": 1.0, "price_output": 3.0, "notes": "核心特性", "source_url": "https://评测页直链"}'

# 只导出国内（用户要求“国内”时的出口）
python <skill_dir>/scripts/export_benchmark_excel.py --scope domestic

# 只导出某公司（可与 --scope 叠加）
python <skill_dir>/scripts/export_benchmark_excel.py --company openai
python <skill_dir>/scripts/export_benchmark_excel.py --scope domestic --company 智谱

# 全部（默认，兼容旧行为）
python <skill_dir>/scripts/export_benchmark_excel.py
```

- 导出器按机构地域自动归类（规则表 `model_taxonomy.py`）；筛选结果为 0 时脚本报错退出，不产出全量文件。
- 排名只在筛选后的集合内计算并从 1 开始；数据不完整的模型不占排名。
- 文件名/表格标题/副标题/底部溯源索引全部随范围联动（例如国内榜：`2026国内主流AI模型综合能力与跑分天梯榜_<YYYYMMDD_HHMMSS>.xlsx`）。

Formula:
Composite Score = (GPQA Diamond × 0.40) + (SWE-bench Verified × 0.35) + (MMLU-Pro × 0.25)

### Stage D: Upload to Google Drive & Deliver (optional)

本地生成并核验通过后，调用 `drive:create_file` 上传：
- Set `title` to the timestamped filename (e.g. `2026国内主流AI模型综合能力与跑分天梯榜_20260908_092612.xlsx`).
- Set `mime_type` to `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- Pass `base64_content` using the `file://` URI referencing the generated file.
- Deliver the Google Drive clickable link (`viewUrl`) to the user. If the environment cannot upload, deliver the local path as-is and say so.