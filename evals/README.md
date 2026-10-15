# 评测说明

本项目还没有证明 Skill 带来普遍收益。不要把格式验证、单个案例通过或记录器输出 PASS 当作行为增益。

## 本次观察

六个任务各一个有/无目标 Skill 的独立配对，两个新任务各一个 v1.1/v1.2 候选版本配对，共 16 份有效回答。两组继承相同父会话的模型设置，没有提供预期答案。

核心观察：两组表现大多接近。加载组的一次文档修改加入了额外条款，但在另一个新案例中原版本也能限制修改范围；不能把它解释成稳定复现的缺陷。两个版本在证据不足的新案例中都能提出补齐对照，候选修订没有表现出独有优势。

完整命令轨迹和运行时模型快照没有从测试工具返回；加载自述未得到独立核验。评分者可见条件，历史由单轮文字描述重放，没有测自动匹配、真实多轮恢复或 Work 运行。这些限制阻止因果和普遍性结论。

## 用例文件

`cases.json` 提供八个历史任务重构和两个新合成保留案例的输入、初始文件与判定标准。八个旧案例并非八份原始真实用户事故记录；两个合成案例也没有真实用户事故来源。来源、先前使用情况和 development / holdout 划分逐案标注。历史观察仍只有上面的 16 份回答，新增案例没有新增行为结果。

标准给评分者使用，不发送给执行模型。保留集已公开，不是秘密测试集；在它上面调过规则后，不应继续声称它是未见案例。

将每个任务放在独立的新目录，两组使用相同初始文件、模型版本、其他指令、推理/采样设置和工具权限，仅改变目标 Skill 的加载条件。不要让下一次执行读到上一次的答案或评分。

## 建议的下一轮

1. 从实际失败收集新的任务，而不是为 Skill 特意构造容易通过的题。
2. 每个任务至少做三次独立配对，打乱组别运行顺序。
3. 捕获实际 Skill 读取与命令执行记录；使用真实文件差异核验修改。
4. 匿名化回答并打乱顺序，再按预先确定的标准评价目标、行动、证据、建议价值及额外内容。
5. 分开报告运行故障、未测、失败、通过以及各配对的胜/平/负；公开退步案例。
6. 检查时间与 Token 成本，最后在目标客户端复测。

公开包提供去除本地路径的摘要和可复现输入，没有包含创建者的私人聊天导出、凭据或原始个人目录。

## 实际运行（Python 3.10+，标准库）

在仓库根目录执行。先复制 `environment.example.json` 并填写真实模型版本、客户端版本、推理设置、工具权限和其他指令。模型身份由你记录，工具不会验证客户端实际用了哪个模型。不要在文件里写密钥。

```sh
python evals/run.py prepare --out evals/artifacts/dev-001 --environment evals/environment.local.json --repetitions 3 --split development
```

这一步只准备 8 × 3 × 2 = 48 个任务，不调用模型、不产生通过结果。每对初始任务文件字节一致，只有加载组包含目标 Skill 和读取指令，运行顺序由固定种子随机化。期望答案和评分标准保存在工作目录外。

准备自己的客户端适配器：它在任务工作目录启动，从 stdin 接收提示词；将最终回答写到 `{response}`，将完整事件轨迹写到 stdout、诊断写到 stderr。命令必须是 JSON argv 数组，不拼接 shell 字符串。`{workspace}` 和 `{response}` 会替换成绝对路径。

`codex-command.example.json` 是 Codex 的起点模板：使用新建临时会话、JSONL 事件与 workspace-write 沙箱，没有跳过审批或沙箱的参数。**运行前把模板复制为本地命令文件，并明确添加与环境记录一致的 `--model` 和推理设置。** 本轮仅核对了本机 CLI 帮助中的参数形状，没有做在线适配器端到端验证。

```sh
python evals/run.py run --out evals/artifacts/dev-001 --command evals/codex-command.local.json --timeout 180
python evals/run.py report --out evals/artifacts/dev-001
```

`run` 才会执行客户端命令、消耗模型额度并按客户端权限操作任务目录。默认逐个运行；每个任务保存 prompt、before/after 文件哈希、原始初始文件、response、trace.jsonl、stderr、changes.diff 与 result.json。成功退出但没有非空回答归为 ERROR；故障和超时保留已有文件。超时停止直接客户端进程，不能保证客户端派生的后台进程都被停止，不应在适配器中启动后台任务。

再次执行会跳过已有 result.json，保留原始失败；需要重试时创建新的实验目录，不把失败覆盖掉。任务尚未执行时为 NOT_RUN。缺少人工评分时为 NOT_RATED；机械 must_change / must_preserve 检查只说明文件变化或保留情况，不评判修改是否正确。`goal_check.py` 仍只是人工结果记录器，没有伪装成执行器。

### 匿名评分和配对统计

```sh
python evals/run.py blind --out evals/artifacts/dev-001 --destination evals/artifacts/review-001
```

把 review-001 单独交给评分者；不要交付原始实验目录和其中的 blind-map.json。按每个样本的标准，将 ratings.json 中的 status 填为 PASS / FAIL / NOT_RUN，并在 evidence 中引用具体回答或文件。匿名包包含任务、标准、回答和任务夹具的前后内容；完整日志和额外文件需要在另一轮证据核验中检查。

```sh
python evals/run.py report --out evals/artifacts/dev-001 --ratings evals/artifacts/review-001/ratings.json
```

只统计运行完成且双方有证据评分的配对，输出 Skill 胜、基线胜、平与未评分/不完整数量。不同的 PASS / FAIL 才算胜负；两组都失败也记平，需另行查看失败类型。不要只展示净胜率或排除故障后隐藏故障数量。人工评分是声明，不由工具认证为真。

开发集完成后冻结规则，再用新的输出目录和 `--split holdout` 准备 2 × 3 × 2 = 12 个任务。若已用保留集调参，应收集新的未见任务。

### 对照的实际限制

- 子进程与目录是实验组织方式，不是文件系统安全隔离。模型可能有读取工作目录外文件的权限；必须检查客户端沙箱、日志和全局 Skill / AGENTS.md / MCP / 插件配置。目标 Skill 若能从全局或祖先目录被基线发现，对照就被污染。
- 工具不清理用户全局配置，不改变登录凭据，也不声称禁止网络或其他 MCP。两组实际权限和模型设置需另外核对。
- 轨迹被保存不代表 Skill 已加载。result.json 始终把 skill_read 标为 NOT_VERIFIED，必须审查成功读取目标文件的真实事件和其上下文；自述和仅出现路径都不够。
- 回答本身可能透露加载条件，因此匿名化不保证评分者完全不知道组别。
- 本轮通过的是本地工具测试；在线模型收益、真实多轮恢复、自动触发、外部用户反馈均不能由这些检查推出。

参数参考：[官方非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)。评测方法参考：[官方 Skills 评测文章](https://developers.openai.com/blog/eval-skills)。

## English protocol summary

Use `prepare` with a completed environment JSON to create randomized baseline/skill pairs. It does not call a model. The eight development cases reconstruct historical tasks; two public holdouts are synthetic extensions, not newly collected user incidents. Freeze instructions before using holdouts and replace them once used for tuning.

Supply a JSON argv adapter accepting the task on stdin and writing the final response to `{response}`. `run` records runtime errors, logs, wall time, snapshots and diffs. The Codex template preserves its sandbox and needs explicit model/settings configuration; live end-to-end adapter behavior has not been verified in this tooling update. Model calls consume the configured account's quota.

`blind` exports anonymous review samples and a NOT_RUN ratings template; keep the label map private from the reviewer. Rate with evidence, then `report --ratings ...` counts paired wins/ties/incomplete cases. Mechanical file checks are separate from human behavioral ratings, neither of which independently establishes general benefit. Audit actual loading, model/settings equality, global instruction contamination, added files and full traces separately. Directory isolation is not a security boundary, and responses may reveal conditions.
