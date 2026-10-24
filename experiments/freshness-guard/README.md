# Freshness Guard：时效核验与 Chat 可靠性实验

[English](README.en.md) · [升级报告](docs/v2.1.0-report.md) · [评测协议](plugin/skills/freshness-guard/references/evaluation.md) · [测试记录](recorded/2026-10-22/)

更新日期：2026-10-22。当前源码版本：2.1.0。

Freshness Guard 是一个可审查的时效事实核验工作流：优先打开官方原文，区分发表、宣布与生效日期，对齐实体、地区、套餐和使用界面，并在证据不足时收窄结论。它还提供离线证据结构检查器及三条件配对评测工具。

目前尚未证明它能够稳定提高普通 Chat 的事实准确率。规则可读、插件可保存、结构测试通过，不等于模型回答更可靠。

## 2.1.0 本轮成果

| 成果 | 实际验证 | 结论范围 |
|---|---|---|
| 修复字段类型导致崩溃 | company/kind/status等无效输入得到错误报告 | 结构检查健壮性，不是事实真假判定 |
| 收紧证据门槛 | 拒绝空白说明、未来发表/修订/抓取日期；来源组归一去重 | 无法自动认证原文语义或采编独立性 |
| 实现三条件对照工具 | 16题×无插件/自然触发/显式调用；冻结随机顺序、原始输出导入、盲评副本、金标准绑定及配对统计 | 工具已实现，真实Chat试次仍为0/48 |
| 回归验证 | 原43项通过；新增14个测试方法通过，包含500次字段类型扰动和15项定向无效输入检查 | 全部是软件/合成测试，不是模型问答准确率 |
| 私人插件更新 | 保存2.1.0并回读14个文件一致 | 不证明当前客户端已加载新版或自动触发 |

当前浏览器能列出ChatGPT页面，但创建/读取状态两次超时，未取得会话交互能力。没有发送真实评测问题；48个计划试次全部pending，比率为null。见[未完成实验报告](recorded/2026-10-22/chat-evaluation-pending/report.json)。

## 目录与复现

- [插件源码](plugin/)：公开脱敏版本；运行规则目前为中文。
- [中文升级报告](docs/v2.1.0-report.md) / [English report](docs/v2.1.0-report.en.md)。
- [中文评测协议](plugin/skills/freshness-guard/references/evaluation.md) / [English protocol](docs/evaluation.en.md)。
- [问题与失误记录](docs/problems.md)、[使用边界](docs/usage.md)。
- [本轮测试与待测计划](recorded/2026-10-22/)、[历史记录](recorded/)、[原v2.0基线](baseline-v2.0/)。

从仓库根目录运行，Python 3.10+，仅标准库：

```sh
python experiments/freshness-guard/plugin/skills/freshness-guard/scripts/run_tests.py
python experiments/freshness-guard/plugin/skills/freshness-guard/scripts/test_upgrade.py
python experiments/freshness-guard/plugin/skills/freshness-guard/scripts/check_evidence.py experiments/freshness-guard/recorded/2026-10-19/live-evidence.json
python experiments/freshness-guard/package.py --output freshness-guard-plugin.zip
```

第三条只检查历史台账结构，不重新核验当前事实。第四条打包公开源码，不负责安装或验证Chat；私人安装链接及账户标识不在仓库中公开。

准备一个新的真实实验（目录必须不存在）：

```sh
python experiments/freshness-guard/plugin/skills/freshness-guard/scripts/evaluate.py init my-chat-experiment --seed 42 --repeats 1
```

该命令只生成计划，不调用模型。按协议采集真实会话和独立评分后再分析；不把缺失、故障或未评分样本改成通过。普通Chat效果验证仍是下一步工作。

2026-10-24：新增[首轮9试次采集手册](docs/chat-pilot-runbook.md)与[本地采集脚本](tools/chat_pilot.py)，复用原48清单，支持普通Chat网页/手机人工采集、发送前金标准冻结、失败留痕和独立评分模板。见[本轮交付与验收](docs/chat-pilot-delivery.md)。当前真实输出仍为0；结构测试通过不等于效果证明。

## 历史成果与局限

2026-10-19保存了16条联网断言记录（14条有限范围verified、2条unknown），另有4问的显式调用试验及一次未点名调用观察。这些来自当时的Work/代理环境，样本少且不具备普通Chat独立随机对照条件，不能汇总为准确率提升或长期自动触发率。历史日期和答案不代表今天的真值。原始CEO错误回答没有完整恢复，事故是用户报告，不冒称已复现。

检查器信任核验者填写的supports_exact、official、origin等字段。即使断言是伪造的，只要标记满足门槛仍可能通过；原测试明确保留了这个边界。它不提供新的联网服务器、执行器或后台监控，也不能修改模型全局行为。

还未完成：普通Chat真实配对与独立评分、长期触发率、真实账户权限验证，以及此前客户端空白/星号原样显示问题的原因定位。降低错误的同时若大量拒答或增加操作负担，也不能直接宣称成功。

## 公开范围与许可

公开源码、合成测试、历史证据、失败记录及未完成计划；省略私人插件ID、邮箱、账户会话链接和个人截图。日志及哈希便于检查副本变化，不是不可伪造的执行证明。中英文件为文档对应版本，英语文档不代表英语行为效果已经测量。沿用仓库[MIT许可证](../../LICENSE)。
