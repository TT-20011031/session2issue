# Session2Issue

**将 Codex 执行任务时的故障记录整理成可核对的 GitHub issue 草稿。**

Session2Issue 是一个本地 Python 命令行工具。它从 Codex JSONL 会话中截取有限的证据，生成英文 Markdown 报告。预期行为、复现步骤和根因需要你自行确认。[English README](README.md)

## 安装

需要 Python 3.11 或更新版本。克隆本仓库后，在仓库根目录执行：

```bash
uv tool install .
session2issue --version
```

如果你使用带 pip 的 Python 环境，也可以运行 `python -m pip install .`。

基础功能不需要 API key，也不会发起网络请求。

## 使用

```bash
session2issue list
session2issue draft --output issue.md
```

工具会列出最近会话和可能的故障事件。你也可以输入 `line N`，指定任意 JSONL 行。已知会话文件和行号时，可以直接运行：

```bash
session2issue draft path/to/rollout.jsonl --line 42 --output issue.md
```

默认在 `$CODEX_HOME/sessions` 和 `$CODEX_HOME/archived_sessions` 查找；`CODEX_HOME` 默认是 `~/.codex`。无交互终端时必须提供文件路径和 `--line`。工具不会覆盖已有报告。

可以先用不含真实信息的样本试用：

```bash
session2issue draft examples/sample.jsonl --line 4 --output sample-issue.md
```

报告包括任务摘录、实际行为、关键错误、附近事件、可用环境信息及隐私检查项。它不会自动判断根因或提交 issue。

## 可选 AI 摘要

先检查并编辑 `issue.md`，然后安装可选依赖，设置 `OPENAI_API_KEY`，运行：

```bash
uv tool install '.[ai]'
session2issue summarize issue.md --output issue.ai.md
```

使用 pip 的环境可改为 `python -m pip install '.[ai]'`。

此命令会在发送前请求确认，只让模型改写标题和简短摘要，并将结果写入新文件。它会把你检查后的草稿发送到 OpenAI API，可能产生费用；基础报告不依赖此步骤。API 请求设置 `store=False`，具体数据处理说明见 [OpenAI 文档](https://developers.openai.com/api/docs/guides/your-data)。

## 分享前请检查

自动遮盖只覆盖常见密钥、邮箱和主目录路径，**不能保证报告没有敏感内容**。请检查提示词、命令、路径和工具输出，确认复现步骤后再分享。原会话文件不会被修改。

开发与贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)，项目采用 [MIT 许可证](LICENSE)。
