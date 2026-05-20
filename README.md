# Live Call Eval MVP

这是 `方案设计2.md` 中“直播升级通知”外呼评测方案的最小可运行版本。

MVP 包含：

- 本地状态机用户模拟器：稳定触发 persona 和探针。
- SUT adapter：支持本地 `scripted`、OpenAI-compatible、Anthropic Messages API。
- Trace 记录：保存每轮 speaker、文本、状态、探针。
- 基础评分器：开场、回复长度、黑名单词、企业微信跟进、优惠券 safety 红线。
- CLI：输出 JSON 报告。

## 快速运行

```powershell
cd c:\Users\afonso\Downloads\live_call_eval_mvp
python .\run_mvp.py --case cooperative --sut scripted
```

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
python .\run_mvp.py --case third_party_invisible --sut scripted --out .\reports\third_party.json
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

## 文件结构

```text
run_mvp.py
src/live_eval_mvp/
  models.py      # trace 与报告数据结构
  simulator.py   # 本地状态机用户模拟器
  sut.py         # scripted / OpenAI / Anthropic adapter
  runner.py      # 两个 agent 的轮流调度
  scorer.py      # MVP 规则评分器
```

## 下一步

- 增加完整 persona 矩阵。
- 增加顺序关键词匹配和步进节奏检测的细分分数。
- 增加数字白名单，检测编造价格。
- 接入 LLM Judge，用于知识点和口语化风格判断。
