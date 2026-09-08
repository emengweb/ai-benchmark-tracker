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

## 环境依赖与安装（Environment Setup — 换设备必读）

脚本主体仅用 Python 标准库 + 少量可选依赖；为保证换到任何设备都能**完整**获取数据
（含渲染型后备源），新环境请按顺序准备：

1. **Python 3.9+**（本技能在 3.12 上测试）与 pip；
2. **核心依赖**（Excel 生成必需）：
   ```bash
   pip install openpyxl
   ```
3. **渲染引擎（可选但强烈建议）**：缺失时 swebench.com / OpenCompass 司南 / Scale SEAL
   三个渲染源自动降级为 unavailable（其余功能不受影响）。
   - 首选 Python Playwright：
     ```bash
     pip install playwright
     playwright install chromium
     ```
   - 回退引擎（Node.js 18+，`render_sources.py` 自动探测全局 npm 路径调用 render_page.cjs）：
     ```bash
     npm install -g playwright
     playwright install chromium
     ```
   - 国内网络下载浏览器慢/失败时使用镜像：
     ```bash
     PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/ playwright install chromium
     ```
4. **安装后自检**（建议执行一次，确认环境完整）：
   ```bash
   # 渲染型后备源（应输出 ocp_* 等观测；无 playwright 时显示 unavailable 属预期降级）
   python <skill_dir>/scripts/render_sources.py --sources opencompass --models "Qwen 3.8 Max"
   # 全流程核验 + 三层后备源（AA 模型页 / OpenRouter 指数 / 渲染榜单）
   python <skill_dir>/scripts/verify_scores.py --fallback
   ```

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

- 排名资格：GPQA Diamond、SWE-bench Verified、MMLU-Pro 三项均有**可用值**（核验 ok / 未核验但有声称值 / 后备源候选值）即计算加权综合得分并参与排名；未核验项在单元格以 `数值⚠`（斜体）呈现并在备注注明。仅两类情况不参与排名：**核验冲突（mismatch，来源值与声称值不一致，需人工复核）** 与 **完全无数值（显示 `—`）**。来源页"未能核验到数值"不等于声称值有误，不允许因此把有声称值的模型踢出排名。
- 完全无数值的运行时新发现模型不挤占主榜，统一进入第 4 张工作表「新发现待核验」（含机构/属性/发布月/发现渠道/来源链接），拿到分数后自动回到主榜。
- `属性` 列承载定位描述（与基线一致的形式：全尺寸旗舰 / 开源权重 / 高吞吐 MoE / 端云结合…）；运行时发现的模型从模型名推导定位词（旗舰 / 轻量 / 预览 / 翻译），推不出时标 `通用`。多模态、定价信息由专列承载，**禁止**在属性列重复写"多模态/商用/免费"。
- 分数核验由 `verify_scores.py` 完成：抓取来源页 → 结构化提取（Score 行 / aria-label / data-target 计数器 / JSON-LD）→ 排除 "Best verified" 参考行 → "模型+指标+数值"三元组比对；结果写回注册表 `verification` 字段，报告输出 `score_verification_report.json`（含证据摘录）与 `verify_pending.json`（人工复核队列）。核验与后备源均采用 ≤6 线程并发 + 每请求超时 + 页面缓存（24h），全量核验通常 2 分钟内完成。
- **禁止**用 SWE-bench Pro、Artificial Analysis Intelligence/Coding Index、Arena Elo 等代理指标顶替或换算这三个基准分。
- 聚合站（benchlm/vals 等）上 "Provider exact / 官方报告" 行才是模型自身分数，"Best verified" 参考行属于其他模型的最优成绩，禁止取用。
- 同一指标在同页存在多个标签化观察值时全部记录（`alt_values`），供人工复核；分数必须有可核验来源并记录来源 URL 与核验时间，网络/动态页面不可获取时如实报告并标记 unverified，绝不编造数据。
- 注册表出现基线字段被覆盖、同名异写重复（GLM 5.3 vs GLM-5.3）、属性列被写成目录标签等历史退化时，运行 `python <skill_dir>/scripts/registry_maintenance.py`（预演）→ `--apply`（写回，自动备份）修复。

## 本地永久存储（缓存）与更新方法

本技能把发现过的模型信息与评分**永久存储在本地**（不是会过期的临时缓存），避免重复查询、加快报告生成：

- 存储位置（技能 scripts 目录内）：
  - `models_registry.json`：模型清单 + 评分 + 核验状态 + **每项评分的来源 URL**（verification / fallback 字段）；
  - `openrouter_models_cache.json`：OpenRouter 目录快照；`openrouter_rankings_hint.json`：月榜热度顺序快照。
- 工作方式：每次运行 `discover_models.py` 联网获取**一次**目录（一次调用），与本地永久存储对比去重——本地已有的模型**不再获取任何数据**，只有 `is_new=true`（本地没有）的新模型才入库、整理、取评分；评分采集完成后再永久写回本地。报告本身从本地注册表生成，速度快、结果稳定。
- 配置文件 `<skill_dir>/config.json`（随技能分发，默认开启）：

```json
{ "cache": { "enabled": true } }
```

  改为 `false` 后忽略本地存储：每次全部候选视为新增并重新取评分（也可单次加 `--no-cache`）。
- **告知义务**：默认流程生成报告时，必须在回复中告知用户"本次数据来自本地永久存储（缓存）"并附更新方法；报告副标题会自动标注数据模式（`--data-mode cache` 默认 / `--data-mode fresh` 本次已刷新）。
- 更新/跳过缓存的提示语范例（用户说法 → 执行方式）：
  - 「更新最新AI模型评分」/「刷新全部评分」→ `discover_models.py --scope all`（目录对比，只处理新增）+ `verify_scores.py --fresh --fallback`（全量重验）+ 导出 `--data-mode fresh`；
  - 「刷新 OpenAI 最新模型/评分」→ `discover_models.py --company openai` + `verify_scores.py --company openai --fresh --fallback` + 导出 `--company openai --data-mode fresh`；
  - 「重新核验 Kimi K3 的评分」→ `verify_scores.py --model "Kimi K3" --fresh --fallback`；
  - 「关闭缓存」→ 编辑 `config.json` 把 `cache.enabled` 改为 `false`（永久生效），或单次命令加 `--no-cache`。

## Dynamic Runtime Model Discovery Workflow

### Stage A: 运行时发现模型（目录 API，非静态清单）

以 OpenRouter 公开模型目录为主源（https://openrouter.ai/api/v1/models，公开 JSON），必要时用月榜页（https://openrouter.ai/rankings?view=month）作热度排序启发。执行本地脚本：

```bash
# 默认：最新/热门模型，热度池默认前 40（--use-rankings 按月榜热度排序，
# 超出月榜可见范围的按最新发布补充；--refresh-hint 强制重取月榜热度）
python <skill_dir>/scripts/discover_models.py --scope all --use-rankings

# 按地域：国内 / 国际（limit 在范围筛选之后截取，40 池保证筛选后有足够候选）
python <skill_dir>/scripts/discover_models.py --scope domestic
python <skill_dir>/scripts/discover_models.py --scope international

# 按公司：公司名可用中文或英文/别名（openai / deepseek / 智谱 / 月之暗面 ...）
python <skill_dir>/scripts/discover_models.py --company openai
```

- `<skill_dir>` is this skill's installed directory (e.g. `~/.zcode/skills/ai-benchmark-tracker`); resolve the actual path at runtime.
- Use `python` on Windows, `python3` on Linux/macOS — check availability if the first attempt fails.
- 输出为 JSON（`summary` + `models`），每条记录含：name、institution、region、multimodal、release_date、price_input/output（$/1M）、source_url（OpenRouter 模型页）、discovered_via（来源/获取时间）、`is_new`（本地永久存储中没有=需要入库/取评分）。**不含伪造分数**。
- 目录每次联网获取一次并与本地永久存储去重；`summary.new_models` 列出新增模型名。**只对新增模型执行入库与取评分，本地已有的直接复用注册表数据。**
- 月榜热度（`--use-rankings`）默认读本地快照（秒级）；`--refresh-hint` 强制重新提取——内嵌数据与 Playwright 渲染两条通道**并行**执行后合并去重（热度覆盖更全），失败自动回退快照。
- 网络失败自动回退本地快照 `openrouter_models_cache.json` 并标注 stale；快照也没有则报错退出。

### Stage B: 自动核验分数（首选）与人工补证

对 Stage A/C 汇总的分数，先运行自动核验脚本：

```bash
# 默认：只核验"没有核验记录的新模型"；已有核验记录的复用本地永久存储结果（含来源URL）
python <skill_dir>/scripts/verify_scores.py --fallback

# 只核验指定模型 / 指定公司（显式指定时忽略缓存强制核验）
python <skill_dir>/scripts/verify_scores.py --model "Kimi K3" --fallback
python <skill_dir>/scripts/verify_scores.py --company openai --fresh --fallback

# 忽略本地永久存储与页面缓存，全部重新核验（用户明确要求更新评分时）
python <skill_dir>/scripts/verify_scores.py --fresh --fallback
```

- 输出 `score_verification_report.json`（逐模型逐指标：ok/mismatch/missing/unverifiable + 证据摘录）与 `verify_pending.json`（人工复核队列）。
- 对核验为 unverified / missing / mismatch 的分数，可先拉取**后备评分源候选值**（不自动升级，供人工复核加速）：

```bash
python <skill_dir>/scripts/benchmark_sources.py                          # 单独拉取后备观测
python <skill_dir>/scripts/render_sources.py --sources swebench,opencompass   # 渲染型后备源（需 playwright）
python <skill_dir>/scripts/verify_scores.py --fallback                  # 核验时同步附加全部后备候选值
```

- 后备源三层结构（`--fallback` 自动依次尝试，单源失败不影响其他）：
  1. **Artificial Analysis 模型页**（GPQA Diamond / MMLU-Pro，RSC 数据流，带家族页重定向守卫）；
  2. **OpenRouter 目录的 AA 三指数**（辅助信号，不进三项基准）；
  3. **渲染型榜单**（需 Playwright 无头浏览器：`pip install playwright && playwright install chromium`，或全局 Node playwright 自动回退）——SWE-bench 官方 Verified 榜单（% RESOLVED）、OpenCompass 司南 LLM 官方榜（均分/知识/推理/数学/代码，中文综合维度辅助指标）、Scale AI SEAL 盲测榜单（按区块标题映射基准）。
- 已实测不可用的源不列入：LMArena API（403）及其 leaderboard 渲染（重定向 arena.ai 后正文为空）、OpenCompass 无渲染的直连、Scale AI parquet（实为任务数据集非成绩）、swebench.com 直连超时（渲染后可用）。
- 对核验为 unverified / missing / mismatch 的分数，再用 `google:search` 搜官方系统卡、基准官方结果页或可复现评测，核对后通过 `--add-model` 更新注册表并重跑核验。
- 查询词：`"<模型名>" "GPQA Diamond" "SWE-bench Verified" "MMLU-Pro" pricing`；国内模型另查 OpenCompass 司南与厂商技术博客。
- 提取字段：GPQA Diamond %、SWE-bench Verified %、SWE-bench Pro %、MMLU-Pro %、输入/输出定价（$/M token）、发布年月、核心定位、以及**每条分数对应的来源直链**；无法核验的分数**留空或保持 ⚠ 未核验状态**（不要臆造）。
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

# 数据模式标注（写入副标题告知用户）：cache=本地永久存储（默认）/ fresh=本次已联网刷新重验
python <skill_dir>/scripts/export_benchmark_excel.py --data-mode fresh
```

- 导出器按机构地域自动归类（规则表 `model_taxonomy.py`）；筛选结果为 0 时脚本报错退出，不产出全量文件。
- 排名只在筛选后的集合内计算并从 1 开始；三项均有可用值（核验 ok / 未核验声称值 / 后备源候选值）的模型参与排名，未核验项标 `数值⚠`；仅核验冲突与完全无数值不占排名（详见"数据完整性与诚实性规则"）。
- 完全无分数的新发现模型进入第 4 张工作表「新发现待核验」，不挤占主榜。
- 文件名/表格标题/副标题/底部溯源索引全部随范围联动（例如国内榜：`2026国内主流AI模型综合能力与跑分天梯榜_<YYYYMMDD_HHMMSS>.xlsx`）。
- 建议流程顺序：`discover_models.py`（目录对比，只处理新增）→ 新模型 `--add-model`（补录）→ `verify_scores.py --fallback`（默认只验新模型）→ 导出（默认 `--data-mode cache`；刷新过则 `--data-mode fresh`）。

Formula:
Composite Score = (GPQA Diamond × 0.40) + (SWE-bench Verified × 0.35) + (MMLU-Pro × 0.25)

### Stage D: Upload to Google Drive & Deliver (optional)

本地生成并核验通过后，调用 `drive:create_file` 上传：
- Set `title` to the timestamped filename (e.g. `2026国内主流AI模型综合能力与跑分天梯榜_20260908_092612.xlsx`).
- Set `mime_type` to `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- Pass `base64_content` using the `file://` URI referencing the generated file.
- Deliver the Google Drive clickable link (`viewUrl`) to the user. If the environment cannot upload, deliver the local path as-is and say so.