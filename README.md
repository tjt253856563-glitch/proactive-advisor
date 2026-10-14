# Proactive Advisor（实验项目）

一套用于减少 AI 助手偏题、只建议不执行，以及没有证据却报告完成的行为约束。适合已有目标下的方案评审、文件修改和任务接续。

**当前没有证据证明它普遍提高了解决问题能力。** 首轮探索性对照中，不加载该 Skill 的模型也能完成大部分关键行为。这个项目公开规则、失败现象和评测方法，邀请真实使用反馈。

Experimental behavior guidance for AI assistants: preserve the user's goal, complete authorized work, and report evidence accurately. General improvement over the baseline has **not** been established.

## 它提供什么

- 保持仍有效的用户目标，服从用户改题和范围限制。
- 在有授权和工具时完成实际修改，而不是只写建议。
- 区分已读取、已执行、已验证与已保存。
- 筛选能影响决策的建议，简单问题直接回答。
- 修正文档时限定范围；证据不足时先补对照，不默认继续堆规则。

它是模型可读取的工作约定，不是执行引擎、权限系统或后台服务。`goal_check.py` 只记录人工提供的检查结果，不运行测试，也不验证证据真假。

## 安装和使用

Skill 文件在 `skills/proactive-advisor/`。将整个目录放入目标客户端支持的 Skills 目录；客户端的发现机制和工具权限需要分别验证。

Codex 的项目级安装示例：把这个目录复制到项目的 `.agents/skills/proactive-advisor/`，随后在新会话中显式调用 `$proactive-advisor`。也可以先不安装，要求助手读取本项目中的 `skills/proactive-advisor/SKILL.md`。

示例请求：

> 使用 $proactive-advisor，检查当前任务是否偏离我的目标。完成已经授权的修正，并告诉我实际修改和检查了什么。

请先验证客户端能发现该 Skill、确实读取了它、行为符合任务要求。文件存在或助手自述“已使用”都不足以证明加载成功。安装到 Codex 也不代表已安装到 ChatGPT Work。

规则以中文编写，包含创建者工作流程中的示例约束。这些例子应结合当前任务使用，不应覆盖用户的新指令。

## 当前评测结果

我们做了六个任务的独立会话配对：不加载目标 Skill 与要求读取 v1.1。另用两个新案例比较 v1.1 和 v1.2 候选，共 16 份有效回答。

- 两组都能保持目标、执行文件修改、服从改题、简短回答和发现测试设计的问题。
- 一次加载组修改文档时，加入了超出必要修正范围的顾问条款。
- v1.2 候选针对修改范围和证据优先顺序做了两处窄修订。
- 新案例中两个版本都能完成任务，候选版没有显示独有优势。

这是小样本、单轮历史重放、评分者知道组别的探索性观察。完整加载轨迹、自动触发、实际 Work 使用以及稳定的相对收益尚未验证。详见 [评测说明](evals/README.md)。

当前目录中的 Skill 是 **v1.2 候选**，不把它标为已经证实优于 v1.1 的版本。

## 欢迎反馈

最有价值的反馈是可以复现的失败案例：

1. 原始任务、必要上下文和预期完成的事情。
2. 客户端、模型及设置，是否确实读取了 Skill。
3. 加载和不加载时的实际回答，或文件修改、命令结果等证据。
4. 哪个具体行为需要改进，例如偏题、扩大修改范围或虚报完成。

请删除账号、凭据、私人对话和业务敏感信息后再提交。只看格式变化、一次通过或 Star 数量，都不能证明规则有效。

## 设计参考

借鉴了 [Superpowers](https://github.com/obra/superpowers) 的工作流思想和 [agent-skills](https://github.com/tronghieu/agent-skills) 对知识工作的处理方式。它不提供这些项目的完整实现，也不是它们的官方扩展。

评测方法参考 [OpenAI 的 Skill 评测说明](https://developers.openai.com/blog/eval-skills)。

## License

MIT，见 [LICENSE](LICENSE)。
