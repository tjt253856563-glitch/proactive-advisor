# Proactive Advisor（实验项目）

[English](README.en.md) · [安装与卸载](docs/installation.md) · [可复现评测](evals/README.md) · [提交反馈](https://github.com/tjt253856563-glitch/proactive-advisor/issues/new/choose)

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

当前先支持 Codex 项目级目录，辅助脚本需要 Python 3.10+。在本仓库根目录运行：

```sh
python scripts/install.py install --project "你的项目绝对路径"
```

脚本复制 `skills/proactive-advisor/` 到目标项目的 `.agents/skills/proactive-advisor/`，核对文件哈希，拒绝覆盖已有目录。在目标项目的新会话中显式调用 `$proactive-advisor`。也可以不安装，要求助手读取本项目的 `skills/proactive-advisor/SKILL.md`。

示例请求：

> 使用 $proactive-advisor，检查当前任务是否偏离我的目标。完成已经授权的修正，并告诉我实际修改和检查了什么。

请先验证客户端能发现该 Skill、确实读取了它、行为符合任务要求。文件存在或助手自述“已使用”都不足以证明加载成功。安装到 Codex 也不代表已安装到 ChatGPT Work。

规则以中文编写，包含创建者工作流程中的示例约束。这些例子应结合当前任务使用，不应覆盖用户的新指令。

卸载：`python scripts/install.py uninstall --project "你的项目绝对路径"`。发现用户修改或新增文件时拒绝自动删除。完整操作和支持边界见 [安装说明](docs/installation.md)。

## 当前评测结果

我们做了六个任务的独立会话配对：不加载目标 Skill 与要求读取 v1.1。另用两个新案例比较 v1.1 和 v1.2 候选，共 16 份有效回答。

- 两组都能保持目标、执行文件修改、服从改题、简短回答和发现测试设计的问题。
- 一次加载组修改文档时，加入了超出必要修正范围的顾问条款。
- v1.2 候选针对修改范围和证据优先顺序做了两处窄修订。
- 新案例中两个版本都能完成任务，候选版没有显示独有优势。

这是小样本、单轮历史重放、评分者知道组别的探索性观察。完整加载轨迹、自动触发、实际 Work 使用以及稳定的相对收益尚未验证。详见 [评测说明](evals/README.md)。

当前目录中的 Skill 是 **v1.2 候选**，不把它标为已经证实优于 v1.1 的版本。

## 可重复运行的项目工具

现在提供十个公开案例：八个先前任务的重构，以及两个尚未用于这轮行为测试的合成保留案例；不冒充十个真实用户事故。标准库评测工具可建立配对目录、随机安排运行顺序、保存输出/命令日志/文件哈希和差异、导出匿名评分包。运行故障、机械文件检查和人工行为评分分别统计；未评分不会变成 PASS。

```sh
python -m unittest discover -s tests -v
```

自动检查覆盖安装与卸载保护、评测隔离、真实文件变化、失败/超时分类和评分证据要求。**这些是项目工具测试，不是新增模型效果结果。** 本轮没有宣称完成新的在线模型对照或外部用户试用。运行方法、客户端配置污染和匿名评分的限制见 [评测操作说明](evals/README.md)。

本机十五项工具测试已通过。GitHub CI 配置覆盖 Windows/Linux 与 Python 3.10/3.12，远程结果以 [Actions](https://github.com/tjt253856563-glitch/proactive-advisor/actions/workflows/checks.yml) 中对应提交的记录为准。检查范围见 [CI 说明](docs/ci.md)。

## 欢迎反馈

最有价值的反馈是可以复现的失败案例：

1. 原始任务、必要上下文和预期完成的事情。
2. 客户端、模型及设置，是否确实读取了 Skill。
3. 加载和不加载时的实际回答，或文件修改、命令结果等证据。
4. 哪个具体行为需要改进，例如偏题、扩大修改范围或虚报完成。

请删除账号、凭据、私人对话和业务敏感信息后再提交。只看格式变化、一次通过或 Star 数量，都不能证明规则有效。

可直接使用 [行为反馈](https://github.com/tjt253856563-glitch/proactive-advisor/issues/new?template=behavior.yml) 或 [安装问题](https://github.com/tjt253856563-glitch/proactive-advisor/issues/new?template=installation.yml) 模板；参与方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 设计参考

借鉴了 [Superpowers](https://github.com/obra/superpowers) 的工作流思想和 [agent-skills](https://github.com/tronghieu/agent-skills) 对知识工作的处理方式。它不提供这些项目的完整实现，也不是它们的官方扩展。

评测方法参考 [OpenAI 的 Skill 评测说明](https://developers.openai.com/blog/eval-skills)。

## License

MIT，见 [LICENSE](LICENSE)。
