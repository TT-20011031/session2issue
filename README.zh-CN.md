# Session2Issue

**将 Codex 执行任务时遇到的问题整理成可核对的 GitHub issue 草稿。**

Session2Issue 是一个 Python 命令行工具。它从 Codex JSONL 会话中整理证据，可离线生成报告提纲，也可根据相关对话上下文用 AI 填写英文完整初稿。用户编辑并核对事实、复现建议及推测后，再决定是否分享。[English README](README.md)

## 安装

需要 Python 3.11 或更新版本。克隆本仓库后，在仓库根目录执行：

```bash
uv tool install .
session2issue --version
```

如果你使用带 pip 的 Python 环境，也可以运行 `python -m pip install .`。

基础功能不需要 API key，也不会发起网络请求。

使用 uv 时，也可以直接运行固定版本：

```bash
uvx --from "git+https://github.com/TT-20011031/session2issue@v0.2.0" session2issue list
```

## 使用

```bash
session2issue list
session2issue draft --output issue.md
```

会话列表显示时间、工作目录的项目名及 Codex 保存的会话标题，例如：

```text
 1. 2026-10-03 10:35  [checkout-service]
    修复结算校验
 2. 2026-10-02 15:20  [demo-app]
    运行测试套件 [task excerpt]
```

标题来自本地 `session_index.jsonl`；没有标题时，从会话文件开头的有限内容中提取首条任务，并标记为 `task excerpt`（任务摘录）。时间为会话文件最后修改时间。`session2issue list --paths` 可额外显示文件路径，`--limit 50` 可列出更多会话。显示的标题和摘录也会进行尽力而为的敏感信息遮盖。

选择会话后，工具会列出可能的问题事件。你也可以输入 `line N`，指定任意 JSONL 行。已知会话文件和行号时，可以直接运行：

```bash
session2issue draft path/to/rollout.jsonl --line 42 --output issue.md
```

默认在 `$CODEX_HOME/sessions` 和 `$CODEX_HOME/archived_sessions` 查找；`CODEX_HOME` 默认是 `~/.codex`。无交互终端时必须提供文件路径和 `--line`。工具不会覆盖已有报告。

### 哪些问题适合整理？

Codex 执行任务期间遇到的各类问题都可能适合：命令或测试报错、工具请求超时、依赖缺失，以及生成的代码不符合要求等。报告可以用于受影响的项目、依赖或工具。

非零退出码和错误文本只是**候选证据**，工具不会据此判断是 Codex 本身的 bug。正常调试中已经修复的报错可能无需提交 issue。只有你确实想报告问题时才选择事件；按 `Ctrl+C` 可以取消。结果不符合预期时可能没有报错，可用 `line N` 手动选择相关记录，再自行补充预期和实际行为。

最近没有遇到问题也可以先用不含真实信息的样本试用：

```bash
session2issue draft examples/sample.jsonl --line 4 --output sample-issue.md
```

离线报告包括任务摘录、关键错误、附近事件、可用环境信息及隐私检查项。此模式的预期行为和复现步骤保留为待填写项。

## 可选：生成完整 AI 初稿

安装可选依赖，在终端环境中设置 `OPENAI_API_KEY`，然后运行：

```bash
uv tool install --force '.[ai]'
session2issue draft --ai --output issue.md
```

在本仓库目录试用合成样本，也可以直接运行：

```bash
uvx --refresh --from '.[ai]' session2issue draft examples/sample.jsonl --line 4 --ai --output issue-trial.md
```

工具会完成会话与问题选择，保存离线备份和上下文预览，再请求确认发送。**先阅读预览文件，再输入 `y`。** 使用 `--output issue.md` 时产生：

| 文件 | 内容 |
| --- | --- |
| `issue.local.md` | 离线证据提纲，AI 失败时仍然保留 |
| `issue.context.md` | 将发送给 API 的脱敏上下文快照 |
| `issue.md` | API 成功且返回内容通过检查后生成的完整初稿 |

完整初稿包括标题、摘要、任务目标、预期和实际行为、复现草稿、已尝试的处理、处理结果、可能原因及待确认问题。主要描述附有来源行号，并区分：

- **Recorded fact**：工具调用或结果直接支持的事实。
- **Reported in conversation**：用户或助手的说法，需要核对。
- **Hypothesis / suggestion**：AI 的推测或建议，需要用户验证。
- **Not recorded**：会话没有提供，需要用户补充。

助手声称“已修复”仅属于对话中的说法。只有后续工具证据才能支持“会话内已有验证”，且仍要检查验证范围。行号引用便于查证，不能保证 AI 理解正确。原始任务摘录、错误证据和环境字段由程序提取。

查看[完整报告示例](examples/sample.ai.md)：它来自合成会话与[模拟 AI 响应](examples/sample.ai.json)，**没有调用真实模型**。其他样本包含[后续验证成功](examples/resolved.jsonl)、[仅声称修复](examples/claimed-fix.jsonl)和[没有工具报错的错误结果](examples/wrong-result.jsonl)。

### 上下文范围

默认从问题发生前最近三条实际用户消息中的最早一条开始，包含之后两轮用户消息及其回复，在第三条后续用户消息之前结束；消息不足时使用文件边界。自动模式也包含相关的较早工具调用。

可用包含边界的 JSONL 行号范围调整：

```bash
session2issue draft path/to/rollout.jsonl --line 42 --ai --context-lines 10:120 --model gpt-6-luna --output issue.md
```

范围必须包含问题行，并在文件内。关联调用位于手动范围之外时会注明缺失。上下文最多 40 个事件、20,000 字符；普通事件最多 2,000 字符，所选事件最多 4,000 字符。问题、关联调用、近期用户要求及窗口末尾的助手总结优先保留。省略和截断情况会明确显示。系统和开发者指令、注入的环境消息、推理记录及图片数据不会进入上下文。

`draft` 的 `--model` 和 `--context-lines` 参数需配合 `--ai`。预览文件用于检查；编辑预览会阻止发送，避免实际发送内容与用户看到的内容不同。需要调整范围时，请使用新的输出文件名重新运行。

### 发送内容与失败处理

完整生成发送的是**上下文预览**，其中包含比离线报告更多的对话内容。原始会话文件、未选择事件及隐藏指令元数据不会上传。敏感信息在截断前遮盖；数量表示截断前执行的遮盖次数，仍需人工检查。

AI 命令需要交互终端，默认模型为 `gpt-6-luna`。每次只请求一次，60 秒超时，不自动重试。API 可能产生费用，请求设置 `store=False`，具体数据处理说明见 [OpenAI 文档](https://developers.openai.com/api/docs/guides/your-data)。

拒绝、取消、缺少依赖或密钥、请求失败、模型拒绝、响应不完整及引用无效时，已经生成的离线备份和预览仍会保留。目标文件存在时拒绝覆盖。AI 失败返回退出码 2，`Ctrl+C` 返回 130。报告不会自动提交到 GitHub。

## 仅改写标题和摘要

先检查并编辑 `issue.md`，然后安装可选依赖，设置 `OPENAI_API_KEY`，运行：

```bash
uv tool install '.[ai]'
session2issue summarize issue.md --output issue.ai.md
```

使用 pip 的环境可改为 `python -m pip install '.[ai]'`。

现有 `summarize` 命令只发送你检查后的 Markdown 草稿，改写标题和简短摘要，证据及其他部分保持原样。它使用相同的默认模型和发送前确认流程。

## 分享前请检查

自动遮盖只覆盖常见密钥、邮箱和主目录路径，**不能保证报告没有敏感内容**。请检查提示词、命令、路径和工具输出，确认复现步骤后再分享。原会话文件不会被修改。

开发与贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)，项目采用 [MIT 许可证](LICENSE)。
