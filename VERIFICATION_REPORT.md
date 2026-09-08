# Benchmark 数据核验报告（2026-09-08）

核验对象：`skill/scripts/export_benchmark_excel.py` 内置基线 18 个模型 × 4 项分数（GPQA Diamond / SWE-bench Verified / SWE-bench Pro / MMLU-Pro）及其 21 个来源 URL。

核验方法：逐个抓取来源页原始 HTML 与纯文本，对"数字是否出现 + 是否归属该模型 + 是否归属该指标"做上下文级核对（含 aria-label / data-target 计数器 / JSON-LD / 内嵌 JSON 等多模式命中），WebFetch 补充验证被风控与 JS 渲染的页面。本节所有"命中"均为上下文确认后的结果，不包含 SVG 路径或时间序列等误报。

## 结论速览

| 结论 | 模型 |
|---|---|
| ✅ 分数在来源页出现且归属正确 | Kimi K3（三项全部）；MiniMax M3（GPQA/MMLU，SWE 数值正确但链接挂错）；Claude Sonnet 5（GPQA）；DeepSeek V4 Flash（MMLU-Pro） |
| ❌ 数值/归属错误（与来源页实际内容冲突） | Qwen 3.8 Max（GPQA）；DeepSeek V4 Flash（GPQA）；DeepSeek V4 Pro（三项全错配）；MiMo-V2.5（全部无出处）；Solar Pro 4（全部无出处）；Nemotron 3 Ultra（全部无出处）；Laguna S 2.1（全部无出处）；Claude Opus 5（全部无出处）；GPT-5.6 Sol（全部无出处）；GPT-5.6 Luna（全部无出处） |
| ❓ 页面存在但无法程序化核验 | GPT-6 Astra（openai.com 403/WAF，WebFetch 超时）；GLM-5.3 / GLM-5.3-Flash（z.ai 博客为 JS 渲染 SPA）；Gemini 3.7 Flash / Hy4 preview（llm-stats 页面无这些分数） |

## 明细

### 1. 核验通过 ✅

**Kimi K3（月之暗面）— 三项全过，是 18 个模型中唯一完整核验的模型**
- GPQA Diamond 93.5%：benchlm.ai/models/kimi-k3 表格 Score 93.5%（"best verified result 96%"）✓
- SWE-bench Verified 93.4%：vals.ai/models/kimi_kimi-k3 页面计数器 data-target="93.40" ✓
- MMLU-Pro 87.2%：benchlm.ai/models/kimi-k3 表格 Score 87.2% ✓
- SWE-bench Pro 65.8%：vals.ai 页未检索到，未核验

**MiniMax M3 — 数值正确，但 SWE 链接归属错误 ⚠️**
- GPQA Diamond 92.9%：requesty.ai 页面 JSON-LD 明确 "Benchmark: GPQA Diamond value: 92.9" ✓
- MMLU-Pro 84.2%：benchlm.ai/models/minimax-m3 表格 Score 84.2% ✓
- SWE-bench Verified 80.5%：数值正确，但**出现在 benchlm.ai/models/minimax-m3（"SWE-bench Verified … Score 80.5%"），而 xlsx 中 [11b] 的 swe_url 却指向 vals.ai/models/minimax_MiniMax-M3——该页根本没有 80.5** → 链接挂错，需改为 benchlm.ai/models/minimax-m3
- SWE-bench Pro 58.2%：未核验

**Claude Sonnet 5（Anthropic）— 仅 GPQA 通过**
- GPQA Diamond 88.9%：benchlm.ai/models/claude-sonnet-5 表格（标注"GPQA Diamond (Vals) Vals AI run Score 88.9%"）✓
- SWE-bench Verified 94.2% / SWE-bench Pro 65.4% / MMLU-Pro 88.5%：该来源页未出现，未核验

**DeepSeek V4 Flash — 仅 MMLU-Pro 通过**
- MMLU-Pro 86.2%：benchlm.ai/models/deepseek-v4-flash-0731 表格（"Provider exact DeepSeek-V4 technical report … Score 86.2%"）✓
- GPQA 88.1%：❌ 见下；SWE-bench Verified 79.0% / SWE-bench Pro 58.6%：来源页未出现

### 2. 数值/归属错误 ❌

**Qwen 3.8 Max（阿里云通义）— GPQA 数值错误**
- 声称 GPQA Diamond 89.4%，来源页（benchlm.ai/models/qwen3-8-max）实际为 **92.6%**："GPQA-D GPQA Diamond Score 92.6% Versus best verified row Best verified: GPT-6 Astra · 96.0%" → 89.4 不是该模型成绩
- SWE-bench 82.5 / SWE-bench Pro 62.5 / MMLU-Pro 88.5：来源页未出现

**DeepSeek V4 Flash — GPQA 把"参考最佳值"当成了自身分**
- 声称 GPQA 88.1%，来源页上下文为 "MCP Atlas Score 69% Versus best verified row **Best verified: Muse Spark 1.1 · 88.1%**" → 88.1 是参考行（其他模型的最好成绩），不是 DeepSeek V4 Flash 的分数

**DeepSeek V4 Pro（深度求索）— 三个指标全部与模型卡内容错配**
- 声称 GPQA 91.2 / SWE-bench Verified 88.6 / MMLU-Pro 88.0，来源为 HuggingFace 模型卡；页面中 88.6 实际出现在 "DROP (F1) 3-shot 88.6"、88.0 出现在 "HellaSwag (EM) 88.0"（标准模型卡评测表），**根本没有 GPQA Diamond、SWE-bench Verified、MMLU-Pro 这三项数值** → 指标错配

**MiMo-V2.5（小米 AI）— 分数无出处**
- 来源为 llm-stats.com 首页：纯文本中无 "mimo" 字样，81.2/72.0/81.6 均未出现；46.5 命中上下文属于 NVIDIA 的置信区间数据 → 全部无出处

**Solar Pro 4（Upstage）— 分数无出处**
- 来源为 benchlm.ai 首页：纯文本无 "Solar Pro" 字样（73.2/81.0 数值存在但无法归属该模型）→ 全部无出处

**Nemotron 3 Ultra（NVIDIA）— 榜单页未收录该模型**
- 来源 labs.scale.com/leaderboard 纯文本无 "nemotron" → 全部无出处

**Laguna S 2.1（Poolside）— 榜单页未收录该模型**
- 来源 benchlm.ai/coding 纯文本无 "laguna" → 全部无出处

**Claude Opus 5（Anthropic）— 官方博客存在但无数值**
- anthropic.com/news/claude-opus-5 页面真实存在（标题 "Introducing Claude Opus 5"），但 95.8/96.5/77.0/91.8 均未出现在页面 → 声称值无出处

**GPT-5.6 Sol（OpenAI）— 官方博客存在但无数值**
- openai.com/index/previewing-gpt-5-6-sol/ 页面确认存在（2026-06-26 "Previewing GPT-5.6 Sol"，含 Sol/Terra/Luna 三模型、Terminal-Bench 2.1 SOTA、GeneBench 等定性描述），但 94.6/96.2/90.1/64.6 均未出现 → 声称值无出处

**GPT-5.6 Luna（OpenAI）— 文档页存在但无数值**
- developers.openai.com/api/docs/models/gpt-5.6-luna 存在（标题 "GPT-5.6 Luna Model | OpenAI API"），但 82.4/74.5/48.2/82.0 均未出现（原始 HTML 中的命中全部为 SVG 路径误报）→ 声称值无出处

### 3. 无法程序化核验 ❓

- **GPT-6 Astra**：openai.com/index/gpt-6-astra/ 直连返回 403（WAF 拦截），WebFetch 超时 → 无法核验
- **GLM-5.3 / GLM-5.3-Flash**：z.ai/blog/glm-5.3(-flash) 为 Vite SPA 壳（HTML 仅含框架与 `glm-5.3-*.js` 资源，正文需浏览器执行 JS），WebFetch 同样拿不到正文 → 无法核验
- **Gemini 3.7 Flash / Hy4 preview**：llm-stats 模型页存在（含定价/上下文），但 86.0/81.2/85.4/52.0 与 92.3/85.4/55.4/86.5 均未在 HTML（含内嵌 JSON）出现 → 页面未呈现这些分数

## 根因分析

1. **基线数据来源不可审计**：早期生成基线时依赖模型口述，无"抓取-提取-比对"环节；
2. **聚合站取值行错误**：benchlm/vals 等页面同时展示 "Provider exact（模型自身官方分）" 与 "Best verified（该指标全站最佳成绩参考行）"，取数时把 **Best verified 参考值当成目标模型分**（Qwen 89.4、DeepSeek V4 Flash 88.1 均因此中招）；
3. **指标名混淆**：把模型卡评测表中的 DROP/HellaSwag 等条目误当 SWE-bench / MMLU-Pro（DeepSeek V4 Pro）；
4. **链接复制错误**：MiniMax 的 swe_url 沿用了 Kimi 的 vals.ai 链接，未与实际数值页面对齐；
5. **把"域名存在"当成"数值可核验"**：OpenAI/Anthropic 官方页、llm-stats、scale.com、benchlm 聚合页普遍是"页面真实但无数值"或"JS 渲染"，此前没有区分这两者。

## 优化方案（按优先级）

1. **核验状态字段入注册表（P0）**：每条分数附带 `verified`（true/mismatch/unverified）、`retrieved_at`、`source_type`（official/leaderboard/independent/aggregator）、`evidence`（命中上下文摘录）。导出器据此降级展示：未核验/冲突分数以斜体 + ⚠ 标注，副标题提示"N 项分数未核验"，与现有"数据不完整"机制共用一套语义。
2. **新增 verify_scores.py 自动核验脚本（P0）**：抓取来源页 → 按本次验证有效的多模式提取（表格 Score、aria-label、data-target 计数器、JSON-LD PropertyValue、内嵌 JSON benchmarks 字段）→ "模型名 + 指标 + 数值"三元组匹配 → 输出 `verification_report.json`（每项：命中/缺失/归属冲突 + 证据摘录 + 检索时间）；导出前自动跑并拦截 mismatch。
3. **聚合站取值规则（P0）**：只取 "Provider exact/官方报告" 与模型专属区间；"Best verified" 参考行与"其余模型对比"区块一律排除；同指标多来源不一致时保留全部观察值，按 official > leaderboard > aggregator 取用并在脚注列出差异。
4. **反爬/JS 渲染站处理（P1）**：openai.com 等 WAF 站点改抓官方新闻页/系统卡 PDF/API 文档的缓存快照；z.ai/llm-stats/scale 解析其内嵌 JSON（已确认 llm-stats 页面含时间序列 JSON，z.ai 有唯一哈希 JS 资源）；两者都拿不到时标记 unverified 计入人工复核队列，不进综合排名展示。
5. **版本化与定期重核（P1）**：每次核验记录 fetched_at + 数值指纹，重核变化 >0.5pt 时告警而非静默覆盖；支持 `verify_scores.py --recheck` 定时任务。
6. **人工复核队列（P2）**：核验失败/冲突项输出 `verify_pending.json`（候选 URL + 缺失原因），人工修订后可回填注册表，形成"自动核验 → 人工裁决"闭环。