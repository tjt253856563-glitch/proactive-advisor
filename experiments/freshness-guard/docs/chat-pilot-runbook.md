# 首轮普通 Chat 采集：3 题 × 3 条件

日期：2026-10-24，Asia/Singapore。对象是 PR #2 的 Freshness Guard 2.1.0，并非仓库主技能 Proactive Advisor 的效果。

当前交付是可开始记录的采集链路，真实 Chat 输出仍为 0。结构测试通过不等于效果证明；没有证明模型效果、自动触发或英文行为改善。

## 1. 冻结范围

依据：[PR #2](https://github.com/tjt253856563-glitch/proactive-advisor/pull/2)，提交 `2aaca6b69a3d5b2862e0688d6a15d271b765a499`；[原协议](../plugin/skills/freshness-guard/references/evaluation.md)与[冻结的 48 试次](../recorded/2026-10-22/chat-evaluation-pending/manifest.json)。不改规则、旧记录和原清单，不重新随机。

看回答前选取冻结顺序中的首道 release、entitlement、stable 题。保留编号和相对顺序；9 试次只是采集可行性子集，原计划未做的 39 条仍 pending。不是随机抽样或效果研究。

| 顺序 | 编号 | 条件 | 只发送这一句话 |
|---|---|---|---|
| 1 | t0001 | implicit | Meta近期公布的模型都属于Llama系列吗？ |
| 2 | t0002 | explicit | Meta近期公布的模型都属于Llama系列吗？ |
| 3 | t0003 | baseline | Meta近期公布的模型都属于Llama系列吗？ |
| 4 | t0004 | baseline | Claude Pro订阅包含API余额吗？ |
| 5 | t0005 | implicit | Claude Pro订阅包含API余额吗？ |
| 6 | t0006 | explicit | Claude Pro订阅包含API余额吗？ |
| 7 | t0013 | explicit | 把“Please close the door.”翻译成中文。 |
| 8 | t0014 | implicit | 把“Please close the door.”翻译成中文。 |
| 9 | t0015 | baseline | 把“Please close the door.”翻译成中文。 |

发布题的“近期”沿用原题：事前金标准须记录当次检索范围、截至时点和解释。有效非 Llama 官方反例可反驳“都属于”，不能事后把未告知的时间窗强加给回答。若题目歧义影响判断就记录，后续另立预注册改题，不能看输出后改标准。不向被测 Chat 发送 rubric、金标准、评分字段和实验说明。翻译题含英文原句不等于测过英文行为。

## 2. 三条件实际操作

先检查当前普通 Chat 界面实际支持什么。不能从“插件已保存”推断“Chat 可用”。

| 条件 | 发送前配置 | 发送动作 | 必留证据 |
|---|---|---|---|
| baseline | 同账号/模型/客户端/套餐/工具；Freshness Guard 对会话不可用；关闭记忆、历史引用、个性化指令，退出带规则项目 | 独立空白普通 Chat，只发 prompt.txt | 无插件配置及会话环境截图，隔离方法 |
| implicit | 同环境；启用同版插件供自动路由，不手选、不点名、不粘贴规则 | 独立空白普通 Chat，只发相同 prompt.txt | 启用版本和会话环境截图；选择与读取分开观察 |
| explicit | 与 implicit 相同配置；用原生选择器手选 Freshness Guard 2.1.0 | 独立空白普通 Chat，手选后只发相同 prompt.txt | 实际手选截图；可见加载轨迹或不可观察原因 |

每次切换后新建会话。若插件为账号全局启用，须确认关闭/重新启用对新会话实际生效。若只能换账号隔离，则账号差异是混杂，不能充作本方案的合格配对。无法关闭同名规则/其他影响路由的插件时，标条件不可用；不要虚填 isolated=true。

三条件全部可实现才启动合格三条件组。保留实际设置截图；模型填 UI 真实标签，底层修订号不显示就明确“界面未显示；底层版本未知”。不能用模型自报版本代替后端版本。

selection_observation=none/natural/manual/unobservable；skill_loaded/searched/opened_original=true/false/null。实际读取只认可见文件/工具轨迹；回答自报、风格和引用不能单独证明加载或搜索。轨迹不可见是 null，不是 false 或 true。手选也不等于实际读取。

同题三条件从首次发送到最后结束最多 900 秒，包含等待、切换与失败重试；准备工作可提前。同组三条的模型、客户端及版本、套餐、工具和插件版本必须匹配，禁止中途换手机/网页/模型。后台版本可能变化仍是局限。

## 3. 超时后的替代采集路径

脚本只留痕，不调用模型，不需要 API key。不再依赖 Work 自动创建/读取页面。

1. 普通 Chat 网页人工新建/发送，用“复制回答”保存全文和引用，同时保留 UI 截图、打印 PDF 或原生导出。trace.txt 记录可见检索/打开轨迹；看不到就注明原因。
2. 自动化超时但网页人工可用：人工完成同一界面采集，记录额外操作。区分自动化访问失败和模型回答失败，不拿等待页时间冒充模型耗时。
3. 网页也不可用：保留失败 run，在手机普通 Chat App 另建 run。只有 App 实际提供全部三条件才开始，整题三条件都用该客户端。要完成首轮验收，建议新 run 完整重采 9 条；旧失败继续披露。
4. 已生成但复制/读取失败：回到原会话恢复首次回答，或用原生账号导出；另记导出取得时间。ended_at 必须仍有生成结束证据，未知就 null，不猜时刻。截图作辅证；OCR 必须逐字核对、说明转录，未核对不算完整原始文本。
5. 原生路径均不可用：NOT_RUN/condition_unavailable，停止本组。API、Work/Codex、粘贴规则和项目上下文只能另立实验，不能替代普通 Chat 自然触发。

访问预算：发送前页面创建/读取最多重试一次，每次 60 秒。两次仍失败则阻塞并切备用路径。发送后不按重新生成、不改问法、不挑答。发送状态 unknown、部分回答和工具错误全部保存。原会话后来恢复时另存补充证据和审查记录，不覆盖已封存失败；本工具不把失败改成通过。新 run 重采须注明父 run/原因。

begin/finish 的命令时间只是记录时间；metadata.started_at/ended_at 来自实际发送/生成观察。统一 ISO 8601 带时区（如 +08:00），未知不代填。

## 4. 初始化目录与命令

仓库根目录，Python 3.10+，仅标准库；Windows 可用 `py -3` 替代 `python`。

```sh
python experiments/freshness-guard/tools/chat_pilot.py init experiments/freshness-guard/runs/pilot-01
python experiments/freshness-guard/tools/chat_pilot.py report experiments/freshness-guard/runs/pilot-01
```

此时第二条必须 exit 2、incomplete、输出 0/9、正确率 null，原 48 计划也 incomplete。重复 init 拒绝覆盖。

```text
pilot-01/
  manifest.json                  原48清单的逐字节副本
  pilot.json                     选题、编号、来源提交、采集脚本/插件哈希
  version/                       冻结的技能源码
  environment.json               操作者/模型/客户端/套餐/工具/隔离和三条件设置
  intake/t0001/prompt.txt         仅发送问题，trial.json 不发送
  gold-drafts/<case>.json         独立核验者待填，默认 independent=false
  gold/<case>.json               发送前冻结的独立金标准
  gold-seals/<case>.json         冻结时间与官方原文/稳定推导哈希
  attempts/t0001/a0001/
    start.json                   条件、环境快照、命令时间、金标准/提问绑定
    sent-prompt.txt              实际发送文字，须与冻结问题一致
    response.txt                 首次完整回答；失败时可保留部分输出
    metadata.json                下表字段，未知保持null
    event.json                   结局、失败原因、发送状态、证据哈希
  evidence/                      设置截图、对话截图/导出、轨迹、官方原文
  raw/t0001.json                 已导入回答与元数据，不能覆写
  imports/t0001.json             原始文件及辅证哈希
  blockers/t0001.json            尚未开始的NOT_RUN及具体原因
  scores.json                    初始为空对象，不默认通过
  report-pilot.json               9试次状态、失败、缺失与描述统计
  report-48.json                  原计划状态；未做的继续pending
```

## 5. 从空模板到第一条真实记录

填 environment.json 的实际配置；设置截图置于 evidence/，路径相对 run 根目录，例如 evidence/baseline-setup.png。available/isolated 只有有依据时改 true；explanation 写具体设置，不能抄方案充作观察。

请独立核验者填写 gold-drafts/meta-release.json。reviewer 用代号且不同于 operator；实际独立才改 independent=true。填 answer/evidence/scope/independence_note、真实 prepared_at/valid_from/valid_until，以及 source_files 相对路径数组。动态题需保存当时官方原文快照、URL、定位、发表/更新/检索日期及范围；稳定题用独立推导文件，不必搜索。金标准作者不能是被测回答模型，不能看被测回答后写标准。没有独立核验者就记录阻塞。本交付不预填动态答案，不冒充评审者。

可以逐题冻结，让金标准窗口覆盖即将执行的三条件：

```sh
python experiments/freshness-guard/tools/chat_pilot.py gold experiments/freshness-guard/runs/pilot-01 meta-release --input experiments/freshness-guard/runs/pilot-01/gold-drafts/meta-release.json
python experiments/freshness-guard/tools/chat_pilot.py begin experiments/freshness-guard/runs/pilot-01 t0001
```

现在才新建普通 Chat 会话，发 intake/t0001/prompt.txt；将首次回答原样保存到 attempts/t0001/a0001/response.txt，并填写同目录 metadata.json。

| 必填/观察字段 | 要保存的事实 |
|---|---|
| model/client/plan/tools | 真实环境，须与 begin 环境一致 |
| session_id | 每试次不同的去标识化会话代号，私密URL不公开 |
| started_at/ended_at | 实际发送/生成结束时刻，带时区；不是导入时间 |
| plugin_version | baseline=none；其余2.1.0；界面版本不能证实则阻塞 |
| selection_observation | none/natural/manual/unobservable；explicit须manual |
| skill_loaded/searched/opened_original | true/false/null；无可见轨迹不推断 |
| trace_ref/observation_notes | 本地trace.txt路径，观察时间、可见轨迹及不可观察原因 |
| isolated/extra_actions | 有证据的隔离声明；实际额外点击/恢复/复制次数 |
| capture_path | chat_web_ui / chat_android_ui / chat_export，与冻结客户端一致 |
| output_complete/output_unedited | 完整且未删改确认；否则incomplete_output |
| evidence_files | 原始UI截图/导出文件相对路径数组，至少一个；不能只用自写摘要 |

成功采集仅表示导入，不代表答对：

```sh
python experiments/freshness-guard/tools/chat_pilot.py finish experiments/freshness-guard/runs/pilot-01 t0001 a0001 --outcome captured --submission sent
```

确实发生超时才用以下示例，access-error.txt 写实际错误、阶段、时间和是否发送：

```sh
python experiments/freshness-guard/tools/chat_pilot.py finish experiments/freshness-guard/runs/pilot-01 t0001 a0001 --outcome page_timeout --submission not_sent --reason "创建页面60秒超时；确认未发送；准备同界面重试" --evidence evidence/access-error.txt
```

失败类型包括 page_timeout/read_timeout/send_unknown/generation_failed/incomplete_output/condition_unavailable/aborted。reason 要具体，不只写“失败”。submission=not_sent/sent/unknown。部分回答、元数据及证据哈希仍保留。一次发送前重试生成 a0002，不覆盖 a0001；发送未知/已发送不能同 run 重试。封存后不回写源文件，新证据另存。

连启动条件都缺失时：

```sh
python experiments/freshness-guard/tools/chat_pilot.py block experiments/freshness-guard/runs/pilot-01 t0001 --reason "填写本次实际缺失前提或访问阻碍"
```

仅写NOT_RUN，不可用来跳题挑答；切路径另立run。依次完成当前组，再为 api-subscription、translation 冻结同期gold并按表采集。

## 6. 独立盲评与报告

```sh
python experiments/freshness-guard/tools/chat_pilot.py blind experiments/freshness-guard/runs/pilot-01 experiments/freshness-guard/runs/pilot-01-blind
```

只导出已有真实回答。给独立评分者的只有 blind 目录，不能附 manifest、环境、条件映射。评分者不得为采集操作者或被测回答产出者；gold作者可兼任，但须披露角色。回答可能自泄露条件，只能称尝试盲法。

scores.template.json 中按实际填写：reviewer、independent、independent_of_response_producer、reason、scored_at；response_sha256/gold_sha256 已绑定副本；不要为另一份回答改哈希。

| 评分字段 | 判定 |
|---|---|
| correct | 全部实质断言正确；证据不足时合理unknown可正确，证据足却拒答为错误 |
| unsupported_certain | 是否有无证据确定性断言，即使碰巧为真 |
| abstained | 是否拒答/保留 |
| unnecessary_search | 稳定题是否多余搜索 |
| fact_changed | 本组三条件期间是否真实变动；剔除并报告，不能隐藏 |
| blinding_broken / blinding_note | 是否识别条件与泄露依据；未知保留null，不能假填false |

reason 提供逐项理由、证据定位、边界。未评字段保持null，不默认false/通过。实际独立评分完成后保存为 run/scores.json：

```sh
python experiments/freshness-guard/tools/chat_pilot.py report experiments/freshness-guard/runs/pilot-01
```

exit 2=未完成；exit 1=输入/完整性错误；exit 0=9试次完整描述统计，绝不等于技能有效。缺输出、未评分、失败、过期gold、事实变动、超900秒、配置不匹配或哈希不符均不算通过。哈希不认证真实性，独立性声明也不能自动认证来源或评分者身份。

## 7. 验收与结论边界

工程验收：空目录能生成冻结清单、9条问题、空模板与incomplete/null报告；能记录超时/发送未知/部分输出，拒绝覆盖、挑答、无独立标准和未评分通过；沿用原评测器。这些是工程/合成测试。

真实链路验收（当前NOT_RUN）：3题各有同模型/客户端/工具、独立会话、900秒内的三条件原始输出；事前独立gold及原文；时间和证据可审查；独立盲评及破盲声明齐全；披露全部失败run、缺失和排除。即使9条完整，也只能说明此次采集链路可行，不能宣布准确率提升、自动触发已解决或英文改善。

只完成9条时，48计划继续incomplete，39条pending。后续全量试验须披露pilot暴露及顺序偏离；不能把这些看过的题当新确认性样本。正式效果主张需另作足量题目、重复策略及独立审查。

报告复制下列模板并按事实填，不预填结果：

```text
实验ID / 父run与重采原因：
来源提交 / 插件版本与哈希 / 采集脚本哈希：
模型标签 / 隐藏版本观察 / 客户端版本 / 套餐 / 工具：
采集者 / gold作者 / 评分者代号及独立性依据：
真实输出：__/9；合格三条件组：__/3；全计划：__/48。
失败尝试/原因/发送状态/重试/全部run位置：
缺输出/未评分/排除理由/事实变化/超窗/配置差异：
逐题差异/耗时/额外操作/拒答/多余搜索：
路由选择/实际读取/检索打开/不可观察/破盲：
结构验证的命令、日志、范围（不写入模型准确率）：
结论：结构测试通过不等于效果证明；本轮仅验采集可行性。
未证明：普通Chat效果、长期自动触发、英文行为改善。
未完成项与下一步：
```

run数据默认不入Git。公开前只制作脱敏副本，注明删改，保留私密原件；账号标识、私密会话URL和个人截图不直接公开。空模板不是执行证明。
