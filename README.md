# AI Benchmark Tracker（ai-benchmark-tracker）

持续追踪、汇总国内外最新 AI 大模型 Benchmark 评测数据：**运行时发现最新/热门模型** → 按用户指定的**范围（国内 / 国际 / 指定公司 / 全部）**筛选 → 采集可核验的 Benchmark 评分 → 加权计算综合得分并排名 → 生成带时间戳的 Excel（.xlsx）天梯榜文档的 Agent Skill。

## 用途与功能

- **范围识别**：自动按用户措辞识别目标范围。`国内/国产/中国` → 仅国内机构（深度求索、智谱、月之暗面、腾讯混元、阿里云通义、MiniMax、小米、百度、字节、阶跃、零一、百川、讯飞、商汤等）；`国际/海外` → 仅海外机构；指定公司名（OpenAI / DeepSeek / 智谱 / 腾讯……）→ 按公司过滤；`国内外/全球/未限定` → 全部。地域按公司/机构信息（中英文别名 + OpenRouter provider slug）自动归类，未识别机构标为 unknown、不会漏进国内/国际范围；
- **运行时发现**：以 OpenRouter 公开模型目录 API（`https://openrouter.ai/api/v1/models`）为主源，实时发现并按时效/热度排序模型（月榜页 `https://openrouter.ai/rankings?view=month` 作尽力而为的热度启发，失败自动回退“最新发布优先”），网络故障自动降级到本地缓存，绝不编造模型；内置 18 个模型基线仅作无网络兜底；
- **诚实评分**：综合得分 = GPQA Diamond × 40% + SWE-bench Verified × 35% + MMLU-Pro × 25%，仅在**三项分数齐全且有效**时计算并参与排名；缺项模型显示 `—` 并标注“数据不完整，未参与综合排名”，不占排名；禁止用 SWE-bench Pro、AI 指数等代理指标顶替三项基准；
- **评分溯源**：“评分来源”列使用下标超链接直指模型评测页，多来源模型（如 Kimi K3 的 [4a]/[4b]）在各分数单元格内分别挂链，模型名称保持纯文本无链接；表格底部溯源索引**随筛选结果动态生成**，国内报表不会出现国际数据源条目；
- **交付物**：带 `YYYYMMDD_HHMMSS` 时间戳后缀的 .xlsx 工作簿（3 个工作表：天梯榜 / 评测基准说明 / 数据源清单），默认生成在当前工作目录；文件名、标题、副标题、排名范围与溯源索引均随所选范围联动。

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
        └── export_benchmark_excel.py    # 合并模型、按范围/公司筛选、计算排名、导出 xlsx
```

> 运行时生成文件（无需手动维护）：`skill/scripts/models_registry.json`（模型注册表，首次运行按内置基线初始化，随 `--add-model` 累积）、`skill/scripts/openrouter_models_cache.json`（发现脚本的最近一次成功目录快照）。

## 调用方法

### 自然语言唤起（推荐）

skill 已内置中文触发语义，**无需提及 skill 名称**。在支持 Agent Skills 的工具（codex / claude / pi / zcode 等）中直接说：

- “整理国内最新 AI 模型 benchmark，汇总成 xlsx 天梯榜” → 只生成国内模型
- “刷新一下国内外主流大模型的跑分数据，生成新的 Excel 报告” → 全部范围
- “整理 OpenAI 公司的 AI 模型评分，汇总成 xlsx” → 只生成 OpenAI 的模型
- “看看最近有哪些新模型发布，把它们的评测分数合并进榜单”
- “更新模型天梯榜并上传到 Google Drive”

Agent 会按 SKILL.md 中的流程执行：解析范围 → 运行时发现模型（OpenRouter 目录）→ 逐模型采集评分证据 → 补录注册表并按范围重算排名 → 生成 xlsx →（可选）上传 Google Drive。用户限定了范围时**不会**回退到全量模型。

### 手动运行脚本

依赖：Python 3.x + openpyxl（`pip install openpyxl`）

```bash
# 1) 运行时发现模型（输出 JSON：summary + models；--company 可与 --scope 叠加）
python skill/scripts/discover_models.py --scope domestic --limit 20
python skill/scripts/discover_models.py --scope domestic --use-rankings --limit 20   # 月榜热度排序（尽力而为）
python skill/scripts/discover_models.py --company openai --limit 20                  # 公司过滤

# 2) 按范围/公司生成天梯榜（默认输出到当前工作目录）
python skill/scripts/export_benchmark_excel.py --scope domestic                      # 仅国内
python skill/scripts/export_benchmark_excel.py --scope international                 # 仅国际
python skill/scripts/export_benchmark_excel.py --company openai                      # 仅 OpenAI
python skill/scripts/export_benchmark_excel.py --scope domestic --company 智谱      # 国内 + 指定公司
python skill/scripts/export_benchmark_excel.py                                       # 全部（默认）

# 3) 补录新模型并重算排名（region 可省略，按机构自动归类；分数未采集到可省略对应字段）
python skill/scripts/export_benchmark_excel.py --add-model '{"name": "模型名", "institution": "机构", "attribute": "属性", "multimodal": true, "release_date": "2026-09", "gpqa": 90.0, "swe_verified": 85.0, "swe_pro": 60.0, "mmlu_pro": 88.0, "price_input": 1.0, "price_output": 3.0, "notes": "核心特性", "source_url": "https://评测页直链"}'

# 指定输出路径
python skill/scripts/export_benchmark_excel.py --scope domestic --output /path/to/report.xlsx
```

说明：

- Windows 用 `python`，Linux/macOS 用 `python3`；
- `--add-model` 合并键为完整模型名；`region` 可选值 domestic/international/unknown，缺省按机构名推断；
- 缺 GPQA/SWE-bench Verified/MMLU-Pro 三项中任意一项分数的记录会以 `—` 呈现并标注缺失项，**不参与综合排名**；
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