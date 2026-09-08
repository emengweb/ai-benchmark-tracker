# AI Benchmark Tracker（ai-benchmark-tracker）

持续追踪、汇总国内外最新 AI 大模型 Benchmark 评测数据：**运行时发现最新/热门模型** → 按用户指定的**范围（国内 / 国际 / 指定公司 / 全部）**筛选 → 采集可核验的 Benchmark 评分 → 加权计算综合得分并排名 → 生成带时间戳的 Excel（.xlsx）天梯榜文档的 Agent Skill。

## 用途与功能

- **范围识别**：自动按用户措辞识别目标范围。`国内/国产/中国` → 仅国内机构（深度求索、智谱、月之暗面、腾讯混元、阿里云通义、MiniMax、小米、百度、字节、阶跃、零一、百川、讯飞、商汤等）；`国际/海外` → 仅海外机构；指定公司名（OpenAI / DeepSeek / 智谱 / 腾讯……）→ 按公司过滤；`国内外/全球/未限定` → 全部。地域按公司/机构信息（中英文别名 + OpenRouter provider slug）自动归类，未识别机构标为 unknown、不会漏进国内/国际范围；
- **运行时发现**：以 OpenRouter 公开模型目录 API（`https://openrouter.ai/api/v1/models`）为主源，实时发现并按时效/热度排序模型（月榜页 `https://openrouter.ai/rankings?view=month` 作尽力而为的热度启发，失败自动回退“最新发布优先”），网络故障自动降级到本地缓存，绝不编造模型；内置 18 个模型基线仅作无网络兜底；
- **诚实评分**：综合得分 = GPQA Diamond × 40% + SWE-bench Verified × 35% + MMLU-Pro × 25%，三项均有可用值（核验 ok / 未核验声称值 / 后备源候选值）即参与排名，未核验项以 `数值⚠` 标注；仅核验冲突（mismatch）与完全无数值（`—`）不占排名；来源页"未能核验到数值"不等于声称值有误，不会把有声称值的模型踢出排名；禁止用 SWE-bench Pro、AI 指数等代理指标顶替三项基准；
- **自动核验**：`verify_scores.py` 抓取每个分数的声称来源页，结构化提取（Score 行 / aria-label / data-target 计数器 / JSON-LD），排除聚合站 "Best verified" 参考行，做"模型+指标+数值"三元组比对；结果写回注册表 `verification` 字段，输出核验报告（含证据摘录）与人工复核队列 `verify_pending.json`；
- **后备评分源**：三层兜底——① Artificial Analysis 模型页（GPQA Diamond / MMLU-Pro）；② OpenRouter 目录 AA 三指数（辅助）；③ **渲染型榜单**（Playwright 无头浏览器渲染 swebench.com / OpenCompass 司南 / Scale AI SEAL，解析渲染后表格）。`verify_scores.py --fallback` 自动把后备候选值附到未核验指标（`fallback` 字段 + pending 队列，**不自动升级为 ok**，人工确认后采纳）；单源失败不影响其他源，家族页重定向/名称前缀误配均有守卫；
- **评分溯源**：“评分来源”列使用下标超链接直指模型评测页，多来源模型（如 Kimi K3 的 [4a]/[4b]）在各分数单元格内分别挂链，模型名称保持纯文本无链接；表格底部溯源索引**随筛选结果动态生成**，国内报表不会出现国际数据源条目；
- **交付物**：带 `YYYYMMDD_HHMMSS` 时间戳后缀的 .xlsx 工作簿（3+1 个工作表：天梯榜 / 评测基准说明 / 数据源清单 / 新发现待核验——完全无分数的运行时新发现模型进第 4 表，不挤占主榜），默认生成在当前工作目录；文件名、标题、副标题、排名范围与溯源索引均随所选范围联动。

## 目录结构

```
ai-benchmark-tracker/
├── README.md                            # 本文档
└── skill/                               # skill 本体（安装时复制此目录）
    ├── SKILL.md                         # skill 定义（frontmatter + 执行指令，含范围识别规则）
    ├── references/
    │   └── datasources.md               # 权威数据源与指标提取规范
    └── scripts/
        ├── model_taxonomy.py            # 机构 -> 公司/地域 分类规则（中英文别名，单一事实来源）
        ├── discover_models.py           # 运行时发现脚本（OpenRouter 目录 + 月榜热度启发 + 缓存降级）
        ├── benchmark_sources.py         # 后备评分源适配器（AA 模型页 GPQA/MMLU-Pro + OpenRouter AA 指数）
        ├── render_sources.py            # 渲染型后备源（Playwright 渲染 swebench/司南/SEAL 后解析表格）
        ├── render_page.cjs              # Node 渲染回退脚本（无 Python playwright 时用全局 Node playwright）
        ├── verify_scores.py             # 分数自动核验（抓取来源页 -> 结构化提取 -> 三元组比对 -> 写回）
        └── export_benchmark_excel.py    # 合并模型、按范围/公司筛选、核验感知排名、导出 xlsx
```

> 运行时生成文件（无需手动维护，均已 gitignore）：`skill/scripts/models_registry.json`（模型注册表，首次运行按内置基线初始化，随 `--add-model` 累积并携带 verification 核验字段）、`skill/scripts/openrouter_models_cache.json`（发现脚本快照）、工作目录下 `score_verification_report.json` / `verify_pending.json` / `.verify_cache/`（核验报告、人工复核队列、页面缓存）。

## 调用方法

### 自然语言唤起（推荐）

skill 已内置中文触发语义，**无需提及 skill 名称**。在支持 Agent Skills 的工具（codex / claude / pi / zcode 等）中直接说：

- “整理国内最新 AI 模型 benchmark，汇总成 xlsx 天梯榜” → 只生成国内模型
- “刷新一下国内外主流大模型的跑分数据，生成新的 Excel 报告” → 全部范围
- “整理 OpenAI 公司的 AI 模型评分，汇总成 xlsx” → 只生成 OpenAI 的模型
- “看看最近有哪些新模型发布，把它们的评测分数合并进榜单”
- “更新模型天梯榜并上传到 Google Drive”

Agent 会按 SKILL.md 中的流程执行：解析范围 → 运行时发现模型（OpenRouter 目录）→ 逐模型采集评分证据 → 补录注册表并按范围重算排名 → 生成 xlsx →（可选）上传 Google Drive。用户限定了范围时**不会**回退到全量模型。

## 依赖与环境准备（换设备必读）

脚本主体基于 Python 标准库；为完整获取数据（含渲染型后备源）需准备：

| 依赖 | 用途 | 安装命令 | 缺失影响 |
|---|---|---|---|
| Python 3.9+ | 全部脚本运行（3.12 测试） | 官网安装包 / `winget install python` | 无法运行 |
| openpyxl | 生成 .xlsx | `pip install openpyxl` | 无法导出 Excel |
| Python Playwright（可选） | 渲染 swebench/司南/SEAL 动态榜 | `pip install playwright` + `playwright install chromium` | 渲染源降级 unavailable |
| Node.js 18+ + 全局 Playwright（可选回退） | render_page.cjs 回退引擎 | `npm install -g playwright` + `playwright install chromium` | 同上（自动回退链路失效） |

国内网络下载浏览器较慢时使用镜像：`PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/ playwright install chromium`

安装后自检：`python skill/scripts/render_sources.py --sources opencompass --models "Qwen 3.8 Max"` 应输出 ocp_* 观测；`python skill/scripts/verify_scores.py --fallback` 应三层后备源全部执行（渲染源在缺 playwright 时显示 unavailable 属预期降级）。

### 手动运行脚本

```bash
# 1) 运行时发现模型（输出 JSON：summary + models；--company 可与 --scope 叠加）
python skill/scripts/discover_models.py --scope domestic --limit 20
python skill/scripts/discover_models.py --scope domestic --use-rankings --limit 20   # 月榜热度排序（尽力而为）
python skill/scripts/discover_models.py --company openai --limit 20                  # 公司过滤

# 2) 自动核验分数（写回注册表 verification 字段；导出前建议先跑）
python skill/scripts/verify_scores.py
python skill/scripts/verify_scores.py --model "Kimi K3"        # 只核验指定模型
python skill/scripts/verify_scores.py --fresh                  # 忽略页面缓存重新抓取
python skill/scripts/verify_scores.py --fallback               # 同时拉取后备源候选值（人工复核用）
python skill/scripts/benchmark_sources.py                      # 单独拉取后备源观测（backup_scores.json）
python skill/scripts/render_sources.py --sources swebench,opencompass   # 渲染型后备源（render_scores.json）

# 3) 按范围/公司生成天梯榜（默认输出到当前工作目录）
python skill/scripts/export_benchmark_excel.py --scope domestic                      # 仅国内
python skill/scripts/export_benchmark_excel.py --scope international                 # 仅国际
python skill/scripts/export_benchmark_excel.py --company openai                      # 仅 OpenAI
python skill/scripts/export_benchmark_excel.py --scope domestic --company 智谱      # 国内 + 指定公司
python skill/scripts/export_benchmark_excel.py                                       # 全部（默认）

# 4) 补录新模型并重算排名（region 可省略，按机构自动归类；分数未采集到可省略对应字段）
python skill/scripts/export_benchmark_excel.py --add-model '{"name": "模型名", "institution": "机构", "attribute": "属性", "multimodal": true, "release_date": "2026-09", "gpqa": 90.0, "swe_verified": 85.0, "swe_pro": 60.0, "mmlu_pro": 88.0, "price_input": 1.0, "price_output": 3.0, "notes": "核心特性", "source_url": "https://评测页直链"}'

# 指定输出路径
python skill/scripts/export_benchmark_excel.py --scope domestic --output /path/to/report.xlsx
```

说明：

- Windows 用 `python`，Linux/macOS 用 `python3`；
- `--add-model` 合并键为完整模型名；`region` 可选值 domestic/international/unknown，缺省按机构名推断；
- GPQA/SWE-bench Verified/MMLU-Pro 三项均有可用值（ok / 未核验声称值 / 后备源候选值）的记录参与综合排名，未核验项标 `数值⚠`（斜体灰）；核验冲突（`数值⚠` 斜体红）与完全无数值（`—`）不占排名；完全无分数的新发现模型进「新发现待核验」表。明细见 `score_verification_report.json`，待人工确认项见 `verify_pending.json`；
- `属性` 列是定位描述（全尺寸旗舰 / 开源权重 / 高吞吐 MoE…），运行时发现的模型按名称推导（旗舰 / 轻量 / 预览 / 翻译，推不出标 `通用`）；多模态与定价有专列，不会在属性列重复；
- 核验/后备源全链路 ≤6 线程并发 + 每请求超时 + 页面缓存（24h TTL），全量核验通常 2 分钟内；
- 若注册表出现基线字段被覆盖、同名异写重复等历史退化，运行 `python skill/scripts/registry_maintenance.py` 预演、加 `--apply` 写回（自动备份到 `.zcode/backups/`）；
- 筛选结果为空时脚本报错退出（exit 2），不会静默导出全量文件。

## 安装方法

将本项目的 `skill/` 目录复制到各平台的 skills 目录下，**复制后的目录名必须是 skill 名称 `ai-benchmark-tracker`**（需与 SKILL.md 中的 `name` 一致，否则无法被识别）。

| 平台 | 目标目录（Windows） | 目标目录（macOS / Linux） |
|------|--------------------|--------------------------|
| codex | `%USERPROFILE%\.codex\skills\ai-benchmark-tracker` | `~/.codex/skills/ai-benchmark-tracker` |
| claude | `%USERPROFILE%\.claude\skills\ai-benchmark-tracker` | `~/.claude/skills/ai-benchmark-tracker` |
| pi | `%USERPROFILE%\.pi\agent\skills\ai-benchmark-tracker` | `~/.pi/agent/skills/ai-benchmark-tracker` |
| zcode | `%USERPROFILE%\.zcode\skills\ai-benchmark-tracker` | `~/.zcode/skills/ai-benchmark-tracker` |

### Git Bash / macOS / Linux

```bash
cd ai-benchmark-tracker
cp -r skill ~/.codex/skills/ai-benchmark-tracker     # 安装到 codex
cp -r skill ~/.claude/skills/ai-benchmark-tracker    # 安装到 claude
cp -r skill ~/.pi/agent/skills/ai-benchmark-tracker  # 安装到 pi
cp -r skill ~/.zcode/skills/ai-benchmark-tracker     # 安装到 zcode
```

### Windows PowerShell

```powershell
cd ai-benchmark-tracker
Copy-Item -Recurse skill "$env:USERPROFILE\.codex\skills\ai-benchmark-tracker"    # 安装到 codex
Copy-Item -Recurse skill "$env:USERPROFILE\.claude\skills\ai-benchmark-tracker"   # 安装到 claude
Copy-Item -Recurse skill "$env:USERPROFILE\.pi\agent\skills\ai-benchmark-tracker" # 安装到 pi
Copy-Item -Recurse skill "$env:USERPROFILE\.zcode\skills\ai-benchmark-tracker"    # 安装到 zcode
```

> 若平台的 `skills` 目录不存在，请先创建（Git Bash：`mkdir -p ~/.claude/skills`；PowerShell：`mkdir "$env:USERPROFILE\.claude\skills"`）。
> 升级已有安装时，直接覆盖复制即可；`models_registry.json` 与缓存是运行时状态，如需保留请勿删除（覆盖复制不会清除它们）。

安装完成后**重启对应工具或开启新会话**即可被识别（skill 列表一般在会话启动时加载）。之后直接用上面的自然语言指令唤起，无需记忆 skill 名称。