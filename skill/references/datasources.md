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

### 聚合站取值规则（防"参考值误当自身分"，P0）

benchlm / vals.ai 等聚合站的指标区块同时含两类数字，取值时**只取模型自身行**：

- **Provider exact / 官方报告行**（形如 `Provider exact <模型> technical report … Score NN.N%`）＝ 模型自身分数；
- **Best verified / best verified result / Versus best verified row** 属参考行，数字归属榜单最佳模型（如 `Best verified: GPT-6 Astra · 96%`），**禁止取用**；
- 专属模型页（页面标题含模型名）上的 `Score NN.N%`、`aria-label`、`data-target` 计数器、JSON-LD `Benchmark: <指标> value NN` 均为有效结构化来源；散文段落中的数字不可作为依据；
- 同一指标在同一页面出现多个标签化数值（例如 Benchmark 自身行与 Vals AI run 行并存）时，全部记录为观察值（`alt_values`）并送人工复核，不静默取一。

### 地域/公司归类

模型的地域按机构（公司）信息判定，规则表见 `scripts/model_taxonomy.py`（中英文别名 + OpenRouter provider slug，例如：DeepSeek/深度求索、Qwen/阿里、Z.ai/z-ai/智谱、Moonshotai/Kimi/月之暗面、Tencent/Hunyuan/腾讯、MiniMax、Xiaomi/MiMo/小米、OpenAI、Anthropic/Claude、Google/DeepMind/Gemini、NVIDIA、Meta、Mistral、xAI、Microsoft、Amazon、Poolside、Upstage 等）。无法识别的机构标记为 `unknown`，不会进入国内/国际范围筛选结果。

