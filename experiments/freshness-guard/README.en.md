# Freshness Guard: freshness checks and Chat reliability experiment

[中文](README.md) · [Upgrade report](docs/v2.1.0-report.en.md) · [Evaluation protocol](docs/evaluation.en.md) · [Test records](recorded/2026-10-22/)

Updated: October 22, 2026. Current source version: 2.1.0.

Freshness Guard is an auditable workflow for facts that can change. It prioritizes opening official sources, separates publication, announcement and effective dates, aligns entities, regions, plans and interfaces, and narrows conclusions when evidence is insufficient. It includes an offline evidence-contract checker and a three-condition paired evaluation tool.

It has not been shown to consistently improve factual accuracy in ordinary Chat. Readable rules, a saved plugin and passing structural tests do not establish more reliable answers.

## What version 2.1.0 delivers

| Deliverable | Observed validation | What it establishes |
|---|---|---|
| Fixes for crashes on invalid field types | Invalid company/kind/status inputs produce validation errors | Checker robustness, not factual truth |
| Stricter evidence gates | Rejects blank explanations and publication/update/crawl dates after retrieval; normalizes declared origin groups | Does not authenticate semantic support or editorial independence |
| Runnable three-condition evaluation | 16 cases × baseline/implicit/explicit; frozen randomized order, raw-response import, blinded copies, gold binding and paired summaries | Tooling exists; real Chat trials remain 0/48 |
| Regression validation | 43 existing checks pass; 14 new test methods pass, including 500 field-type mutations and 15 targeted invalid-input checks | Software and synthetic tests, not model accuracy measurements |
| Private plugin update | Version 2.1.0 saved; 14 files read back consistently | Does not prove the current client loaded the update or invoked it automatically |

The available browser listed a ChatGPT page, but page creation/state reading timed out twice. No interactive Chat trial was obtained and no evaluation question was submitted. All 48 planned trials are pending; rates are null. See the [incomplete experiment report](recorded/2026-10-22/chat-evaluation-pending/report.json).

## Contents and reproduction

- [Plugin source](plugin/): sanitized public source; runtime instructions are currently in Chinese.
- [English upgrade report](docs/v2.1.0-report.en.md) / [中文报告](docs/v2.1.0-report.md).
- [English evaluation protocol](docs/evaluation.en.md) / [中文协议](plugin/skills/freshness-guard/references/evaluation.md).
- [Problem and failure records, Chinese](docs/problems.md), [usage boundaries, Chinese](docs/usage.md).
- [Current tests and pending schedule](recorded/2026-10-22/), [historical records](recorded/), [v2.0 baseline](baseline-v2.0/).

From the repository root, using Python 3.10+ and only the standard library:

```sh
python experiments/freshness-guard/plugin/skills/freshness-guard/scripts/run_tests.py
python experiments/freshness-guard/plugin/skills/freshness-guard/scripts/test_upgrade.py
python experiments/freshness-guard/plugin/skills/freshness-guard/scripts/check_evidence.py experiments/freshness-guard/recorded/2026-10-19/live-evidence.json
python experiments/freshness-guard/package.py --output freshness-guard-plugin.zip
```

The third command validates historical structure without rechecking present-day facts. The fourth packages public source; it does not install the plugin or verify Chat behavior. Private installation links and account identifiers are not published here.

Prepare a new real experiment in a directory that does not exist:

```sh
python experiments/freshness-guard/plugin/skills/freshness-guard/scripts/evaluate.py init my-chat-experiment --seed 42 --repeats 1
```

This only generates a plan; it does not call a model. Collect real sessions and independent judgments according to the protocol before analyzing them. Missing outputs, tool failures and unscored responses are not passes. Real Chat efficacy evaluation remains future work.

## Historical evidence and limitations

Records from October 19 contain 16 web-checked claims: 14 classified as verified within limited scopes, and two unknown. Separate observations include an explicit-invocation trial with four questions and one implicit-invocation observation. These used the then-available Work/agent environment, were small and lacked an independent randomized ordinary-Chat comparison. They cannot be combined into accuracy improvement or long-term invocation rates. Historical dates and answers are not present-day ground truth. The original reported CEO error was not fully recovered and is not claimed as a reproduced failure.

The checker trusts reviewer-supplied fields such as supports_exact, official and origin. A fabricated claim may still pass if those declarations satisfy the gates; the existing tests deliberately retain this boundary probe. The plugin does not add a retrieval server, executor or background monitor, and does not change global model behavior.

Outstanding work includes actual ordinary-Chat paired trials and independent scoring, long-term triggering measurements, real-account entitlement verification, and diagnosis of previously reported blank/spinning replies and literal asterisk rendering. Fewer errors accompanied by excessive abstention or extra user effort would not by itself establish success.

## Publication scope and license

This directory publishes source, synthetic tests, historical evidence, failures and pending plans. Private plugin IDs, email addresses, private session links and personal screenshots are omitted. Logs and hashes help detect changed copies; they are not tamper-proof execution attestations. English documentation is a counterpart to the Chinese documentation, not evidence of evaluated English-language behavior. Licensed under the repository's [MIT license](../../LICENSE).
