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

更多场景（均可用 `--sut scripted`，无需 API）：

第三方未显示：

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

## 配置与 API（.env）

安装依赖并配置密钥（**推荐只维护 `.env`**，`run_mvp.py` 启动时自动加载；终端里的 `$env:XXX` 优先级更高）：

```powershell
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env
```

### 三个组件

| 组件 | CLI | 默认 | 环境变量前缀 | 说明 |
|------|-----|------|----------------|------|
| 被测客服 SUT | `--sut scripted\|openai\|anthropic` | `scripted` | `SUT_*` | 本地脚本无需密钥 |
| 用户模拟器 | `--simulator local\|llm\|hybrid` | `local` | `SIMULATOR_*` | 推荐 `hybrid`（探针走状态机） |
| 裁判 | `--judge off\|llm` | `off` | `JUDGE_*` | `llm` 覆写语义类 rubric |

`.env.example` 中已列出常用项：`API_KEY`、`MODEL`、`PROTOCOL`（`openai` / `anthropic`）、`API_BASE_URL`、`MAX_TOKENS` 等。建议 `SIMULATOR_MAX_TOKENS` 与 `JUDGE_MAX_TOKENS` 设为 `1024`。

### 推荐命令（真实模型全链路）

```powershell
python .\run_mvp.py --case cooperative --sut anthropic --simulator hybrid --judge llm
python .\run_mvp.py --run-all --sut anthropic --simulator hybrid --judge llm --save-individual --html
```

### 协议与 CLI 覆盖

- **Anthropic**：`SUT_API_BASE_URL` 填网关根地址（不要带 `/v1/messages`）。首轮历史为空时会自动插入占位 user 消息，不写入 trace。
- **OpenAI 兼容**：`--sut openai`，`SUT_API_BASE_URL` 一般为 `https://api.openai.com/v1`。
- 模拟器 / Judge 的 `*_PROTOCOL` 与 SUT 相同；也可用 CLI 覆盖，例如 `--model`、`--api-base-url`、`--simulator-model`、`--judge-model`。

Judge 覆盖的 rubric 列表见 `src/live_eval_mvp/judge.py` 中的 `LLM_JUDGE_CRITERIA`。

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

## 文件结构

```text
run_mvp.py              # 主入口
render_report.py        # JSON → HTML
.env.example            # 密钥模板（复制为 .env，勿提交）
tasks/cases.yaml        # persona / 探针 / 期望分支
requirements.txt
src/live_eval_mvp/
  env.py                # 自动加载 .env
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
  report_html.py        # HTML 报告渲染
reports/                # 本地输出（已在 .gitignore，不提交 Git）
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

指定输出路径或生成 HTML：

```powershell
python .\run_mvp.py --run-all --sut anthropic --out .\reports\summary_run.json --html
```

## HTML 报告

加 `--html` 在与 JSON 同目录生成同名 `.html`；或对已有 JSON：`python .\render_report.py .\reports\summary_xxx.json`。用浏览器打开即可查看。

## 后续计划

- 扩展 persona（方案中更多边界场景）
- 汇总报告 HTML 顶部展示 `simulator` / `judge` 后端（与 JSON 字段对齐）
- 可选：流程节点可视化、与竞赛平台对接
