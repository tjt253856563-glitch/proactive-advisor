# 上下文承接实验 / Context follow-through

用户正在比较同一道题的 A/B 回答，说“总结一下”时，助手却可能重新回答原题。这份实验把该失误描述变成可重放的上下文任务，并提供一份专门处理这类问题的技能草稿。

**目前没有观察到额外收益，也没有在本轮 Codex 重放中复现原先 Work 的偏题。** 本目录是实验成果，不是已验证的修复或正式发布的新技能。项目默认安装的 Proactive Advisor v1.2 候选未改变。

## 这次做了什么

| 任务 | 不加载目标规则 | intent-check | Proactive Advisor v1.1 |
|---|---|---|---|
| A/B 回答后说“总结一下” | 通过 | 通过 | 通过 |
| 明确改为三句话总结技术方案 | 通过 | 通过 | 通过 |
| 讨论对照结果后问“接下来怎么弄” | 通过 | 通过 | 通过 |

共九次实际执行，每个格子一次；它们共享同一组材料，不是九个独立用户事故。六次加载组的成功工具输出均包含完整规则。评分由维护者按事先固定的案例标准检查，非独立盲评。

两份原始 A/B 回答已保留在 [conversation.md](conversation.md)。开场、简短总结请求和控制题是重构或合成内容，**不是失败轮逐字复现**；开场明确给出比较目标，可能使任务更容易。三类任务分别检查承接、改题与后续推进。没有测试 Work 自动调用、真实满意度或实际返工。

- [规则草稿](candidate/context-followthrough/SKILL.md)：区分当前对象、操作和任务；服从明确改题。格式校验通过，未参与九次对照，尚未行为验证，也未自动安装。
- [测试结果与限制](测试结果.md)：说明这轮能证明和不能证明的事。
- [案例和标准](cases.json)、[冻结计划](plan.md)：标准不发送给执行模型。
- [实际回答与结果](recorded/results.json)、[评分依据](recorded/ratings.json)、[加载证据](recorded/loading-audit.json)：保留工具命令及输出，创建者本机目录身份已替换。
- `rules/`：本轮测试用的固定规则副本，不代表这些技能会自动被当前客户端调用。

## 重跑

需要 Python 3.10+ 和已经登录的 Codex CLI；会产生正常的模型用量。沿用运行者自己的默认模型和用户配置，本次记录的 CLI 版本见 [runtime.txt](recorded/runtime.txt)。完整服务器模型快照未独立核验。

在本目录执行：

```sh
python evaluate.py prepare --repeats 2
python evaluate.py run
python evaluate.py report
```

默认准备三条件、三案例，每格两次，共 18 次；不加载 `candidate/` 中的草稿。生成的 `runs/` 含本机原始运行日志，只供本地检查；`evidence/` 导出工具事件和可见回答。行为结果默认 `NOT_GRADED`，不会把运行成功当成行为通过。需要人工阅读回答并依据案例标准评分。

已有 `manifest.json` 时，`run` 只补做没有结果的执行，`report` 可重新生成导出。需要新实验时，将 `evaluate.py`、`conversation.md`、`cases.json`、`rules/` 复制到新的独立目录，不带旧的运行结果和评分，再运行。`recorded/` 是本次历史快照，不参与新运行。

脚本在子进程配置中禁用本机全局安装的 intent-check，加载组显式读取工作区副本；其余用户配置保留，不能视为完整环境隔离。Windows 下可继承本机回环代理配置。每个子进程最多运行 180 秒；运行权限和用量由当前 Codex 客户端控制。

## English summary

This is an exploratory reconstruction of a reported failure: when asked to summarize two answers in a skill evaluation, an assistant answered the underlying technical question instead. The original two answers are retained, while the framing and follow-up messages are reconstructed or synthetic.

Nine live Codex runs covered three tasks under baseline, intent-check, and Proactive Advisor v1.1. All passed maintainer review; full rule reads were observed in all six loaded runs. No incremental benefit was established, and the Work failure was not reproduced. The focused candidate skill passed format validation but was not behavior-tested or installed. It is separate from the project's default skill. The runner supports new trials; archived answers, ratings, and redacted tool evidence are in `recorded/`.
