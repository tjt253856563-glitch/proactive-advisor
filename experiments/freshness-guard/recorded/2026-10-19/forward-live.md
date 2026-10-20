# Freshness Guard 实际联网核验

截至 Asia/Singapore 2026-10-19 14:05:44（UTC 06:05:44；本轮检查时间，不代表整日无后续事件）。已读取指定 SKILL.md、references/sources.md、references/evidence.md；没有编辑 Skill。

## 回答

1. **GPT-6.1 Sol 已发布；Plus 在普通 Chat 与 Work 权限不同。** OpenAI 原始公告 Pricing and availability 明确列出 Plus、Pro、Business、Enterprise、Edu 可在 ChatGPT Work 与 Codex 使用，并说尚不在 Chat。当前帮助页继续明确 GPT-6.1 Sol 不可在普通 Chat 使用、正在向合格付费计划 rollout，仍受计划、工作区设置及 rollout access 限制。因此是计划级资格确认，不是所有 Plus 账户已实测可用。普通 Chat 的 GPT-6 Sol 与 GPT-6.1 Sol 不得混淆。**原始公告可见正文未公开文章日期，精确官方发布日期 unknown**；不能把 today、2026 分类、第三方 Copilot 上线日期当成 OpenAI 发布日。
2. **Gemini 4 Argon 首次官方宣布日为 2026-09-30，当时为受限分阶段开放；2026-10-13 是 Gemini App 中向 Google AI Pro/Ultra 订阅者开放的日期。** 两个日期对应不同事件。不能说现在免费用户都能用：已打开的 App 公告支持付费订阅者，不支持全球免费账户全面开放。本轮面向 support.google.com 的 Argon/free 检索未获得适用的当前权限正文；免费计划完整现状及各地区、年龄、账户限制为 unknown，未实测账户。
3. **Anthropic 最近能确认的一次模型发布为 Claude Haiku 5.5，2026-10-07。** 打开原文的日期、介绍与 Availability 均明确；Newsroom 可见模型卡片同样列出 10/7 Haiku 5.5、9/28 Sonnet 5.5、9/22 Opus 5.5。仅称本轮已确认的一次发布，不保证涵盖所有渠道的绝对最新。
4. **Meta 能确认的模型发布已不止 Llama。** 官方原文明确推出 Muse Wonder、Muse Wonder Full；Wonder 当日通过 Meta Model API 与 Muse Code 提供，Wonder Full 面向 Muse Code 订阅者。该页头部同时出现 2026-10-12 与 2026-10-13，工具没有给这两个日期语义标签；可确认官方于该日期区间公告发布，但精确事件日 unknown，不擅自认定一个为发表、另一个为修订。页面还说未来才进入 Muse 产品、先向订阅者 rollout，不能扩写成所有用户可用或开放权重。

## 官方来源及正文定位

| ID | URL | 已打开正文证据 | 日期与范围 |
|---|---|---|---|
| O1 | https://openai.com/index/introducing-gpt-6-1-sol/ | turn10view0 L35 宣布；L113–114 Pricing and availability | 文章日期 null；today 缺少锚点 |
| O2 | https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex | turn14view1 L19–25，L37–48 | 当前页面；文章发表/修订精确日期 null；计划而非账户 |
| O3 | https://help.openai.com/en/articles/20001354-gpt-6-and-other-models-in-chatgpt | turn14view0 L80–93 | 当前页面，区分 Chat 与 Work/Codex |
| G1 | https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/ | turn13view0 L214–249 | 2026-09-30 宣布，Fairwind 有限 rollout |
| G2 | https://blog.google/innovation-and-ai/products/gemini-app/gemini-4-argon-availability/ | turn13view1 L210–222 | 2026-10-13；Google AI Pro/Ultra；无全球免费权限证明 |
| A1 | https://www.anthropic.com/claude-haiku-5-5 | turn14view2 L150–152、turn15view2 L17–27 | 2026-10-07 日期，模型已发布 |
| A2 | https://www.anthropic.com/news?cam=claude | turn14view3 L17–18、L25–34 | 本轮可见 Newsroom，有 10/18 非模型新闻；不保证全渠道完整 |
| M1 | https://about.fb.com/news/2026/10/introducing-muse-wonder-models/ | turn15view0 L239–252 | 页头 2026-10-12/13 双日期，语义未标注；API/Muse Code 发布 |

## 真实工具过程（关键轨迹）

- 本机读取 `<skill-root>/SKILL.md` 与上列两个 references 文件。
- 检索工具：`mcp__codex_apps__search_service_web_run`；访问方式是检索服务的页面抽取，**不是无缓存直连官网**。搜索结果大多标为 Crawled today，抓取具体时分 unknown，不把它当发布日期。
- 第一轮 system1（recency 90/60）：`site:openai.com "GPT-6.1" "Sol"`、`site:blog.google "Gemini 4" "Argon"`、`site:anthropic.com/news model release`、`site:ai.meta.com OR site:about.fb.com "model" "Muse"`。OpenAI 精确公告命中；Google/Meta/Anthropic 结果混有导航及旧文相关卡片，不直接当正文证据。
- 原文 open：OpenAI 公告、Anthropic Newsroom、Google AI 频道、Meta Blog。Meta Blog open 返回 Internal Error，未据此推断无新模型。
- 第二轮 system1：OpenAI Help Plus 精确查询结果明显无关；Google Gemini 4 Argon release 找到 9/30 与 10/13 两条公告；Meta 查询找到 Wonder 模型卡片入口。
- 适应性切换 system2：`site:help.openai.com "GPT-6.1 Sol"` 命中当前帮助原文；`site:anthropic.com/news "Claude Haiku 5.5"` 命中独立模型公告。随后 open O2/O3/A1/A2，并从 Meta Newsroom 第 205 页实际 click 到 M1。
- 继续 open/find 核对 M1 的 Takeaways/October，A1 的 October；确认 Meta 双日期未标注、Anthropic 明确 10/7。Google `site:support.google.com/gemini "Argon" free` 第一轮返回无关结果；不将其作为无免费权限的否定证据，以 G2 公告为可支持范围后停止。
- 未访问用户账户、未付费或注册、未执行实际模型调用。
- 检查命令读取 `scripts/check_evidence.py` 返回 No such file or directory；**未执行验证脚本**。采用 evidence.md 人工检查：官方来源、正文打开、事件与发表日期区分、unknown、计划级范围、未声称绝对最新。

## 限制

本轮已打开并可定位的官方正文支持发布存在和上述特定渠道资格；搜索覆盖及缓存版本不保证全网或整日完整。OpenAI 发布日期缺失、Meta 双日期语义、Google 免费完整权限均保留 unknown。不存在“今天没有发布”的全网否定结论。

## 后续结构检查

最初读取脚本确实返回缺失，以上保留当时观察。收到父代理通知文件已补齐后，已另外生成同目录 `forward-live.json`（7 条断言），并实际执行：

`python <skill-root>/scripts/check_evidence.py <workspace>/evidence/forward-live.json`

结果 `ok: true`、`errors: []`、7 claims、6 verified。警告 3 条：o-release、o-access 与 m-release 有来源发布日期未知，不得据检索日推断。g-free 保持 unknown。检查仅验证结构与申明门槛，不证明语义准确或来源真实。最终结论没有为配合任何预期答案而改写。
