# 普通 Chat 三条件配对评测

本工具只准备实验、导入原始回答、导出盲评副本、计算描述统计，不调用模型，不创建 Chat 会话，不把计划当作执行结果。不能用 Codex/Work 的代理回答替代普通 Chat。

## 冻结与执行

从 skill 目录运行 Python 3.10+（仅标准库）：

```sh
python scripts/evaluate.py init experiment --seed 42 --repeats 1
```

得到16题×3条件=48个计划试次。题目、顺序和题目哈希保存在 manifest.json；重复运行拒绝覆盖。每题内部三条件随机顺序，题目顺序随机。固定 seed 是可复现实验计划，不代表结果已独立或随机抽样。

按顺序在同一普通 Chat 模型、客户端、套餐、工具组合下执行，每试次独立新会话。baseline：没有加载 Freshness Guard；implicit：安装相同版本、自然提问不点名；explicit：显式选择同版本插件。提问文字保持不变。不要要求 baseline 遵守插件，也不要在自然触发条件中暗示先读规则。无法隔离全局指令/记忆/既有插件时 isolated=false，并披露，不能计为合格配对。三条件的开始至结束总窗口最多900秒；需要不同阈值时应在实验开始前另行设计并记录理由。

执行前由独立核验者保存 gold/<case_id>.json：

```json
{
  "reviewer": "独立评分者代号",
  "independent": true,
  "answer": "按本次时点核验的答案，动态问题不能预填永久答案",
  "evidence": "官方原文链接、定位、日期与适用范围；稳定题说明推导",
  "valid_from": "2026-10-22T10:00:00+08:00",
  "valid_until": "2026-10-22T10:15:00+08:00"
}
```

时间仅为格式示例，须换成本次有效窗口；valid_until 是评测者为本次实验声明的范围，不是网站保证的事实有效期。保存原文及检索轨迹，对时间窗内真实变动设 fact_changed=true。官网失败不能自动将错误答案判正确。缺独立核验者时可保留待评，不能把同一回答模型自评标 independent。

## 导入与留痕

保存真实原始回答到 response.txt，元数据到 metadata.json：

```json
{
  "model": "界面显示的实际模型",
  "client": "实际客户端与版本",
  "plan": "本次套餐",
  "tools": "本次可用工具集合",
  "session_id": "去标识化且每试次不同的会话代号",
  "started_at": "2026-10-22T10:00:00+08:00",
  "ended_at": "2026-10-22T10:01:00+08:00",
  "trace_ref": "本地原始轨迹文件或不可观察原因",
  "plugin_version": "2.1.0",
  "skill_loaded": null,
  "searched": null,
  "opened_original": null,
  "extra_actions": 0,
  "isolated": true
}
```

baseline 的 plugin_version 填 none。三项轨迹观察值允许 true/false/null；null 为不可观察，不能自动判作未触发。日志是核验者声明，哈希只检测副本变化，不认证真实性。不要公开账号、会话私密链接、密钥和个人截图。

```sh
python scripts/evaluate.py import experiment t0001 --response response.txt --metadata metadata.json
python scripts/evaluate.py blind experiment blind-review
```

盲评副本移除条件与运行元数据，保留题目、原始回答、金标准。回答自己可能透露插件条件，因此是尝试盲评，不保证完全盲法；由另外的评分者审阅副本并记录破盲。

## 评分与报告

scores.json 是 blind_id 到评分对象的映射；每份评分需：reviewer、independent=true、reason、response_sha256、gold_sha256，以及布尔值 correct、unsupported_certain、abstained、unnecessary_search、fact_changed。response_sha256 从盲评副本取；gold_sha256 为 evaluate.digest(gold对象) 的值。未评保持不存在，不能默认通过。

correct 按整题所有实质断言评分；unknown 在证据确实不足时可为正确，同时 abstained=true；证据已充分却拒答算 correct=false。unsupported_certain 表示存在至少一个无证据的确定性事实断言，即使它碰巧为真。unnecessary_search 只在 stable 题统计。事实变化剔除且展示，不掩盖失败。工具故障保留原始输出，未完成不改为通过。

```sh
python scripts/evaluate.py analyze experiment --scores scores.json --output report.json
```

缺输出、未评分、缺金标准、哈希不符、同会话复用、模型/客户端/套餐/工具不一致、插件版本不一致、超时窗等会阻止完整配对。退出码2表示实验未完成；0仅表示描述性报告完整，不表示插件有效。空数据的比率为 null，不是0%或100%。只对合格三条件配对计算结果；同时显示排除、缺失、unknown、不可观察数、耗时和额外操作。

paired_differences_vs_baseline 给出同题差值（正确率向上较好，无依据断言/拒答/多余搜索向下较好），不能把少量试次宣传成解决可靠性。Wilson区间是逐试次描述，重复同题不独立；正式推断需按题聚类、样本量计划和独立审查。工具永远不自动给“效果已证明”的结论。

运行 `python scripts/test_upgrade.py` 测工具边界。其合成输出只存在临时目录，不能导入真实实验充数。
