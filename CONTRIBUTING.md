# 贡献与试用反馈 / Contributing

欢迎提供可复现失败、安装问题和小范围修正。请先用一个具体任务试用：在相同模型、设置、工具权限和必要上下文下，分别运行不加载与加载 Skill 的独立会话，保留两组输出。不要把上一次回答或评分给下一次执行模型。

提交前删除凭据、账号、私人聊天、业务资料及个人绝对路径。没有授权的真实对话不要上传；可以提供标明“重构”或“合成”的最小案例。不要把合成案例写成真实用户事故。

- 行为失败：使用 [行为反馈模板](https://github.com/tjt253856563-glitch/proactive-advisor/issues/new?template=behavior.yml)，说明期望行为、实际行为和证据。未运行的组别请明确填写 NOT_RUN。
- 安装问题：使用 [安装问题模板](https://github.com/tjt253856563-glitch/proactive-advisor/issues/new?template=installation.yml)，附客户端版本、Python 版本、命令和去隐私后的报错。
- 代码贡献：先运行 `python -m unittest discover -s tests -v`。新增规则需要对应失败证据，保留不相关的有效条款，避免为单个例子增加通用长流程。

评测请读 [evals/README.md](evals/README.md)。公开结果时同时报告退步、运行故障、未评分和成本。当前没有承诺回应时间，也没有已经完成的外部试用人数。

English: report a minimal redacted task, exact client/model/settings, actual outputs and artifact differences. Keep baseline and treatment sessions independent. Label reconstructed and synthetic examples honestly. Missing runs are NOT_RUN. Infrastructure tests, a star or a single successful answer do not demonstrate a behavioral benefit. Run the unittest command above before contributing code; justify instruction changes with observed failures.
