# 证据格式与门槛

根对象包含 `as_of`（带时区 ISO 时间）、`claims` 数组。每条至少包含：
`id, company, kind, claim, status, scope, sources, conflict, limitation`。
kind 为 release / entitlement / leadership / other；status 为 verified / corroborated / provisional / unknown。
来源包含 `url, official, opened, retrieval_at, published_at, event_at, date_note, locator, supports_exact, current_scope, origin`。
其中时间未知用 null，date_note 解释缺失或日期精度；locator 保存章节/行号定位或不超过 25 英文词的短引文；origin 是独立采编来源组标识。official、supports_exact、current_scope 由核验者根据正文判断，脚本无法证明这些布尔值。

权限断言另含 `access_level`（announcement / plan / account），scope 必须写出界面、套餐、地区；声称 account 必须含 `account_observed: true`。不要把账户身份信息写入台账。
`conflict: true` 表示未消解冲突，此时 status 只能 unknown。解决后的冲突用 false，并在 `resolution` 保存来源、范围与更新理由。
`absence_claim: true` 的记录必须限定检查范围并包含 `checked_channels`，即使如此 verified 也只代表该范围内的观察。

`as_of` 是检查截止，不是知识保证有效期。跨轮复用旧证据时先检查断言波动程度及有无新线索，权限和高管的“现在”问题应当轮重新读取当前官方页；历史发布可复用带日期的原文。不设虚假的统一 24 小时有效期。

运行 `check_evidence.py` 只检查结构与已声明的证据门槛，无法检测伪造的日志或语义错配。保存检索工具轨迹供人工/独立代理复核，不将同一模型的自评作为独立准确率。

v2.1.0补充：limitation/date_note须为字符串，要求解释时不能仅有空白。locator/origin须为非空文本；origin按去空白和大小写折叠去重，但仍不能自动证明采编独立。absence_claim/account_observed只接受布尔值，checked_channels在absence_claim=true时须为非空字符串数组。event_phase如提供，须为announced/planned/effective。发布日期、修订日与抓取日不得晚于retrieval_at；只含日期时按检索时间所声明时区的日历日期比较，不编造时分。未来event_at允许作为预告，不能标为已生效。所有这些仍是离线结构门槛。
