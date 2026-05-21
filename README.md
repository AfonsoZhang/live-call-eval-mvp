# Live Call Eval MVP

这是 `方案设计2.md` 中“直播升级通知”外呼评测方案的最小可运行版本。

MVP 包含：

- 用户模拟器：`local`（状态机）、`llm`（LLM API）、`hybrid`（探针/强制句走状态机，其余走 LLM）。
- SUT adapter：支持本地 `scripted`、OpenAI-compatible、Anthropic Messages API。
- Trace 记录：保存每轮 speaker、文本、状态、探针。
- 规则评分器 + 可选 **LLM Judge**：对语义类 rubric 用 LLM 覆写关键词判定。
- CLI：单 case 或 `--run-all` 批量，输出 JSON / HTML 报告。

## 快速运行

```powershell
cd path/to/live_call_eval_mvp
python .\run_mvp.py --case cooperative --sut scripted
```

## 配置密钥（.env）

1. 安装依赖：`pip install -r requirements.txt`
2. 复制 `copy .env.example .env`，编辑 `.env` 填入密钥（勿提交 `.env`）。建议 `SIMULATOR_MAX_TOKENS` 与 `JUDGE_MAX_TOKENS` 均为 `1024`。

3. 直接运行 `python .\run_mvp.py ...` 时会**自动加载**项目根目录下的 `.env`。
   - 已在终端里设置的 `$env:XXX` **优先**（不会被 `.env` 覆盖）。
   - `--sut scripted` 且 `--simulator local`、`--judge off` 时无需配置密钥。

第三方系统未显示场景：

```powershell
python .\run_mvp.py --case third_party_invisible --sut scripted
```

优惠券红线场景：

```powershell
python .\run_mvp.py --case discount --sut scripted
```

写入报告文件：

```powershell
python .\run_mvp.py --case third_party_invisible --sut scripted --out .\reports\third_party_invisible.json
```

## 接入 Anthropic API（推荐）

使用 Anthropic Messages API（`POST /v1/messages`）：

```powershell
$env:ANTHROPIC_API_KEY="your_anthropic_key"
$env:SUT_MODEL="claude-sonnet-4-20250514"

python .\run_mvp.py --case cooperative --sut anthropic
```

也支持统一环境变量名：

```powershell
$env:SUT_API_KEY="your_anthropic_key"
$env:SUT_MODEL="claude-sonnet-4-20250514"
$env:SUT_API_BASE_URL="https://api.anthropic.com"
$env:SUT_ANTHROPIC_VERSION="2023-06-01"
$env:SUT_MAX_TOKENS="1024"

python .\run_mvp.py --case cooperative --sut anthropic
```

参数覆盖示例：

```powershell
python .\run_mvp.py --case cooperative --sut anthropic --model claude-sonnet-4-20250514 --max-tokens 512
```

首轮外呼时历史为空，Anthropic 要求 `messages` 至少一条；MVP 会自动插入占位 user 消息「（电话已接通，请按外呼任务开场。）」，不会写入最终 trace。

若使用 Anthropic 兼容网关，把 `--api-base-url` 设为网关根地址（不要带 `/v1/messages`）：

```powershell
python .\run_mvp.py --case cooperative --sut anthropic --api-base-url https://your-gateway.example.com
```

## 接入 OpenAI-compatible API

```powershell
$env:SUT_API_KEY="your_api_key"
$env:SUT_MODEL="your_model"
$env:SUT_API_BASE_URL="https://api.openai.com/v1"

python .\run_mvp.py --case cooperative --sut openai
```

也可以用参数覆盖模型和 base URL：

```powershell
python .\run_mvp.py --case cooperative --sut openai --model your_model --api-base-url https://example.com/v1
```

## 用户模拟器 LLM API

三种模式：`--simulator local|llm|hybrid`（推荐 `hybrid`：探针仍由状态机保证触发）。

环境变量前缀 `SIMULATOR_*`（与 SUT 相同协议：`openai` / `anthropic`）：

```powershell
$env:SIMULATOR_API_KEY="your_key"
$env:SIMULATOR_MODEL="your_model"
$env:SIMULATOR_PROTOCOL="anthropic"
$env:SIMULATOR_API_BASE_URL="https://your-gateway.example.com"

python .\run_mvp.py --case cooperative --sut anthropic --simulator hybrid
```

CLI 可覆盖：

```powershell
python .\run_mvp.py --case third_party_invisible --sut anthropic `
  --simulator hybrid --simulator-protocol anthropic --simulator-model your_model
```

## LLM Judge API

`--judge off`（默认，纯规则）或 `--judge llm`（对已触发的语义 rubric 调用 Judge 覆写得分）。

环境变量前缀 `JUDGE_*`：

```powershell
$env:JUDGE_API_KEY="your_key"
$env:JUDGE_MODEL="your_model"
$env:JUDGE_PROTOCOL="anthropic"
$env:JUDGE_API_BASE_URL="https://your-gateway.example.com"

python .\run_mvp.py --case cooperative --sut anthropic --simulator hybrid --judge llm
```

Judge 覆盖的 rubric 见 `src/live_eval_mvp/judge.py` 中 `LLM_JUDGE_CRITERIA`（开场、step2/3/4、身份分支、开车/忙碌边界、优惠拒绝、FAQ 延迟等）。

密钥与模型名写在项目根目录 `.env` 即可，无需每次在 PowerShell 里 `$env:...`。

## Case 配置（tasks/cases.yaml）

6 个 persona 已从代码抽到 `tasks/cases.yaml`，包含：

- `id` / `persona` / `flow`（`cooperative` | `third_party`）
- `expected_branch`：期望覆盖的流程节点
- `probes`：探针（`min_turn`、话术、是否只触发一次）
- `first_reply`：首轮回合特殊话术（如非负责人）

列出全部 case：

```powershell
python -c "import sys; sys.path.insert(0,'src'); from live_eval_mvp import list_case_ids; print(list_case_ids())"
```

指定自定义 cases 文件：

```powershell
python .\run_mvp.py --case driving --cases .\tasks\cases.yaml --sut scripted
```

安装依赖：

```powershell
pip install -r requirements.txt
```

## 文件结构

```text
run_mvp.py
tasks/cases.yaml          # persona / 探针 / 期望分支
requirements.txt
src/live_eval_mvp/
  cases.py              # 加载 YAML case 定义
  models.py             # trace 与报告数据结构
  simulator.py          # 本地状态机用户模拟器
  user_simulator_llm.py # LLM / Hybrid 用户模拟器
  simulator_factory.py  # create_simulator(local|llm|hybrid)
  llm_client.py         # 共享 OpenAI / Anthropic 调用
  judge.py              # LLM Judge 与 rubric 标准
  sut.py                # scripted / OpenAI / Anthropic adapter
  runner.py             # 两个 agent 的轮流调度
  scorer.py             # 规则评分 + 可选 LLM Judge
  batch.py              # 批量跑 case
```

## 评分维度（Phase 2）

报告 JSON 现包含 `dimension_scores`：

| 维度 | 含义 |
|------|------|
| `completion` | 流程覆盖：开场、step2/3/4/6/7、身份转达、FAQ 延迟 |
| `safety` | 红线：拒绝优惠、禁止编造价格数字 |
| `robustness` | 边界与节奏：开车挂断、说忙挽留、步进引导分轮 |
| `style_constraint` | 每轮字数、黑名单词 |

触发型规则未触发时不计入该维度分母。失败项汇总在 `violations`。

## 批量评测（`--run-all`）

一次跑完 `tasks/cases.yaml` 中的全部 persona，并生成汇总报告：

```powershell
python .\run_mvp.py --run-all --sut scripted --save-individual
```

输出默认：`reports/summary_YYYYMMDD.json`，包含：

- `mean_task_score` / `mean_dimension_scores`
- `by_persona`：每个 persona 得分与违规数
- `rubric_fail_rate`：各 rubric 失败率
- `results`：每个 case 的完整报告

指定输出路径：

```powershell
python .\run_mvp.py --run-all --sut anthropic --out .\reports\summary_run.json
```

真实 SUT 批量（需已配置 API）：

```powershell
$env:SUT_API_KEY="..."
$env:SUT_MODEL="your_model_name"
$env:SUT_API_BASE_URL="https://your-gateway.example.com"
python .\run_mvp.py --run-all --sut anthropic --simulator hybrid --judge llm --save-individual
```

## HTML 报告（浏览器查看）

跑评测时顺带生成 HTML（与 JSON 同目录、同名 `.html`）：

```powershell
python .\run_mvp.py --case cooperative --sut scripted --out .\reports\cooperative.json --html
python .\run_mvp.py --run-all --sut scripted --html
```

已有 JSON 可单独转换：

```powershell
python .\render_report.py .\reports\summary_test.json
python .\render_report.py .\reports\cooperative.json .\reports\driving.json
```

用浏览器打开生成的 `.html` 即可：汇总表、各 case 展开详情、对话气泡、规则与违规列表。

## 下一步

- Pass^3：`--trials 3` 已支持 `pass_at_k`。
