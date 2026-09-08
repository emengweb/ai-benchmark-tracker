\# 权威 AI Benchmark 数据源规范与提取指南



本参考文档规定了在采集与更新大模型评测数据时必须遵循的权威来源、指标定义及解析规则。



\## 1. 核心数据源地址与指标对应关系



| 维度 | 数据源平台 | 权威 URL | 核心提取指标 |

| :--- | :--- | :--- | :--- |

| \*\*工程落地与真实生产力\*\* | SWE-bench (普林斯顿) | https://www.swebench.com/ | SWE-bench Verified (%), SWE-bench Pro (%) |

| \*\*综合智能与 API 性能\*\* | Artificial Analysis | https://artificialanalysis.ai/ | Intelligence Index, TTFT, Tokens/s, 价格 ($/M) |

| \*\*高阶科学学术推理\*\* | Scale AI SEAL Labs | https://labs.scale.com/leaderboard | GPQA Diamond (%), Humanity's Last Exam (%) |

| \*\*前沿数学与逻辑极限\*\* | Epoch AI | https://epoch.ai/frontiermath | FrontierMath (%) |

| \*\*实时防污染代码编程\*\* | LiveBench | https://livebench.ai/ | LiveCodeBench (%), 动态多维度打分 |

| \*\*盲测对战与真实人类偏好\*\*| LMSYS Chatbot Arena | https://huggingface.co/spaces/lmarena-ai/arena-leaderboard | Arena Elo 积分, Arena-Hard 胜率 (%) |

| \*\*国内双语与中文基准\*\* | OpenCompass 司南 | https://rank.opencompass.org.cn/ | C-Eval (%), CMMLU (%), 中文综合得分 |

| \*\*运行时模型目录（发现主源）\*\* | OpenRouter Models API | https://openrouter.ai/api/v1/models | 模型 id/名称/上下文长度/多模态/定价($/M)/发布时间（公开 JSON，无需鉴权） |

| \*\*热度排序启发（尽力而为）\*\* | OpenRouter 月榜 | https://openrouter.ai/rankings?view=month | 月使用量 Top 榜；页面为动态渲染，无稳定公开 JSON 接口，仅作排序启发，失败自动回退 |

### 运行时发现与动态页面边界（重要）

- **目录 API 与榜单页的区别**：`/api/v1/models` 是稳定公开 JSON，是模型发现的主源；`/rankings` 是 Next.js 动态页面，本技能只在 `--use-rankings` 时做“首次出现顺序”正则提取作为热度启发，提取失败必须回退并在输出中标注 `ranking_source`，不得冒充月榜排名。
- **数据集 ≠ 成绩接口**：SWE-bench Verified（Hugging Face `SWE-bench/SWE-bench_Verified`）、MMLU-Pro（`TIGER-Lab/MMLU-Pro`）、GPQA（github.com/idavidrein/gpqa）等公开的只是评测任务数据与评测代码，不是模型实时得分；禁止用“数据集可下载”暗示拿到了模型成绩。
- **禁止指标替换**：Artificial Analysis 的 Intelligence/Coding/Agentic Index、LMSYS Arena Elo、LiveBench 分数都不能换算或顶替 GPQA Diamond / SWE-bench Verified / MMLU-Pro 三项基准分；代理指标只能作为补充信息展示。
- **降级与诚实**：SWE-bench Pro 与 Verified 是不同评测族，不得互相填充；动态源（Artificial Analysis、Scale SEAL、OpenCompass）不可获取时输出结构化状态（unavailable_dynamic_source / rate_limited / schema_changed），保留最近一次已验证快照并标注 stale，绝不静默覆盖或编造分数。



\## 2. 一期目标模型清单 (Phase 1 Target Models)



\### 国内主流开源 / 商用模型

\- \*\*DeepSeek\*\*: DeepSeek V4 Pro, DeepSeek V4 Flash (0731/0423)

\- \*\*阿里云通义 (Alibaba Qwen)\*\*: Qwen 3.8 Max, QwQ-32B

\- \*\*智谱 AI (Zhipu / Z.ai)\*\*: GLM-5.3, GLM-5.3-Flash

\- \*\*月之暗面 (Moonshot AI)\*\*: Kimi K3, Kimi k1.5

\- \*\*腾讯混元 (Tencent Hunyuan)\*\*: Hy4 preview, Hy3

\- \*\*MiniMax\*\*: MiniMax M3

\- \*\*小米 AI (Xiaomi)\*\*: MiMo-V2.5



\### 国际头部 Top 20 旗舰模型

\- \*\*OpenAI\*\*: GPT-6 Astra, GPT-5.6 Sol, GPT-5.6 Luna, OpenAI o1, o3-mini

\- \*\*Anthropic\*\*: Claude Opus 5, Claude Sonnet 5, Claude 3.7 Sonnet

\- \*\*Google\*\*: Gemini 3.7 Flash, Gemini 2.0 Pro

\- \*\*NVIDIA\*\*: Nemotron 3 Ultra

\- \*\*Poolside\*\*: Laguna S 2.1

\- \*\*Upstage\*\*: Solar Pro 4



\## 3. 综合评测得分计算规则



采用无偏加权三维综合模型：

\- \*\*GPQA Diamond (博士级高阶学科推理)\*\*：权重 40% (0.40)

\- \*\*SWE-bench Verified (真实软件工程闭环能力)\*\*：权重 35% (0.35)

\- \*\*MMLU-Pro (多学科综合知识与抗干扰能力)\*\*：权重 25% (0.25)



计算公式：

$$\\text{综合得分} = (\\text{GPQA Diamond} \\times 0.40) + (\\text{SWE-bench Verified} \\times 0.35) + (\\text{MMLU-Pro} \\times 0.25)$$



排序规则：完全依据综合得分进行数学降序排列，且仅在筛选后的目标集合内排位（国内/国际/指定公司榜单各自从 1 开始）；三项分数任一缺失或无效的模型不参与综合排名，在表格中显式标注并排在完整记录之后。

### 后备评分源适配器（benchmark_sources.py，兜底候选值）

当声称来源无法核验（403 / JS 渲染 / 页面无值）时，从以下源拉取标准化观测作为**人工复核候选**（`--fallback` 写入注册表 fallback 字段 + pending 队列，不自动升级 ok）：

| 适配器 | 数据源 | 覆盖指标 | 说明 |
| --- | --- | --- | --- |
| artificial_analysis | https://artificialanalysis.ai/models/\<slug\> | GPQA Diamond, MMLU-Pro | 解析 RSC 数据流的 `gpqa`/`mmmuPro` 字段（0-1 归一）；带家族页重定向守卫（如 /models/glm-5-3-flash 重定向到 /models/glm-5-3 时拒绝采用） |
| openrouter_indices | https://openrouter.ai/api/v1/models | AA 三指数（辅助） | `benchmarks.artificial_analysis` 的 intelligence/coding/agentic index，**仅辅助信号，不可顶替三项基准** |

已实测**不可用**、勿再尝试的候选（如实记录探测结论）：LMArena API（`lmarena.ai/api/*` → 403 Forbidden）与 LMArena leaderboard 渲染（重定向 arena.ai 后正文为空）；OpenCompass 司南直连（全站 SPA，无公开 JSON 接口，**渲染后可用**，见下）；Scale AI SWE-bench Pro 的 HF space parquet（`lhoestq/ScaleAI-SWE-bench_Pro-atlas`，实为评测**任务数据集**：repo/instance_id/patch 列，不是模型成绩）。上述源的分数需浏览器渲染或人工取证后录入。

### 渲染型后备源（render_sources.py，Playwright 无头浏览器）

对无稳定 JSON 的动态榜单页，用 Playwright 渲染后解析正文表格（`pip install playwright && playwright install chromium`；无 Python 包时自动回退全局 Node playwright）：

| 源 | 渲染 URL | 解析指标 | 说明 |
| --- | --- | --- | --- |
| swebench | https://www.swebench.com/ | SWE-bench Verified（% RESOLVED） | CSS 网格表（每单元格一行），官方 Verified 榜单，分数含 agent 配置 |
| opencompass | https://rank.opencompass.org.cn/leaderboard/llm | 均分/知识/推理/数学/代码（ocp_*） | 司南 LLM 官方榜；中文综合维度，**辅助指标**，非 GPQA/SWE/MMLU |
| scale_seal | https://labs.scale.com/leaderboard | 按区块标题映射（SWE→swe_verified、SWE Atlas→swe_pro、GPQA→gpqa、HLE→hle、FrontierMath→frontiermath） | 分数带 ± 误差；区块标题无法判定时记 aux_seal |

渲染结果与 benchmark_sources 同构（model_display/metric/value/source/source_type/source_url），`verify_scores.py --fallback` 一并采纳为人工复核候选；渲染失败（timeout/empty_page/重定向）如实记录 status，不影响其他源。

### 聚合站取值规则（防"参考值误当自身分"，P0）

benchlm / vals.ai 等聚合站的指标区块同时含两类数字，取值时**只取模型自身行**：

- **Provider exact / 官方报告行**（形如 `Provider exact <模型> technical report … Score NN.N%`）＝ 模型自身分数；
- **Best verified / best verified result / Versus best verified row** 属参考行，数字归属榜单最佳模型（如 `Best verified: GPT-6 Astra · 96%`），**禁止取用**；
- 专属模型页（页面标题含模型名）上的 `Score NN.N%`、`aria-label`、`data-target` 计数器、JSON-LD `Benchmark: <指标> value NN` 均为有效结构化来源；散文段落中的数字不可作为依据；
- 同一指标在同一页面出现多个标签化数值（例如 Benchmark 自身行与 Vals AI run 行并存）时，全部记录为观察值（`alt_values`）并送人工复核，不静默取一。

### 地域/公司归类

模型的地域按机构（公司）信息判定，规则表见 `scripts/model_taxonomy.py`（中英文别名 + OpenRouter provider slug，例如：DeepSeek/深度求索、Qwen/阿里、Z.ai/z-ai/智谱、Moonshotai/Kimi/月之暗面、Tencent/Hunyuan/腾讯、MiniMax、Xiaomi/MiMo/小米、OpenAI、Anthropic/Claude、Google/DeepMind/Gemini、NVIDIA、Meta、Mistral、xAI、Microsoft、Amazon、Poolside、Upstage 等）。无法识别的机构标记为 `unknown`，不会进入国内/国际范围筛选结果。

