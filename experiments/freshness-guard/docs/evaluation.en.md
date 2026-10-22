# Ordinary-Chat paired evaluation protocol

[中文](../plugin/skills/freshness-guard/references/evaluation.md) · [Overview](../README.en.md) · [Upgrade report](v2.1.0-report.en.md)

The tool prepares an experiment, imports raw responses, exports blinded copies and computes descriptive statistics. It does not call a model or create Chat sessions. A planned run is not an executed trial, and Codex/Work agent outputs must not substitute for ordinary Chat.

## Freeze cases and execute sessions

Use Python 3.10+ and the standard library. Run the following from the skill directory, `experiments/freshness-guard/plugin/skills/freshness-guard/`:

```sh
python scripts/evaluate.py init experiment --seed 42 --repeats 1
```

This creates 16 cases × three conditions = 48 scheduled trials. Case content, case hashes, randomized order and schedule hashes are frozen in manifest.json; an existing directory is not overwritten. The seed makes the plan reproducible, not the evidence independent or representative.

Run each trial in a separate new ordinary-Chat session using the same model, client, plan and available tool configuration. Keep the question text unchanged:

1. baseline: Freshness Guard is not loaded.
2. implicit: the same plugin version is installed, but the question does not name it.
3. explicit: explicitly select that plugin version before asking the question.

Do not instruct baseline sessions to obey the plugin or hint at reading its rules in implicit sessions. Record `isolated=false` if prior instructions, memory or other loaded plugins prevent isolation. Such trials are not eligible pairs. Each three-condition case must fit within 900 seconds from the earliest start to the latest finish. A different window requires a separately documented design before execution.

Before execution, an independent reviewer saves `gold/<case_id>.json` containing:

```json
{
  "reviewer": "independent-reviewer-code",
  "independent": true,
  "answer": "Answer verified for this observation window",
  "evidence": "Official source URLs, locations, dates and applicable scope; reasoning for stable cases",
  "valid_from": "2026-10-22T10:00:00+08:00",
  "valid_until": "2026-10-22T10:15:00+08:00"
}
```

Dates are examples, not reusable validity guarantees. Replace them with the actual observation window. Preserve source text and retrieval traces. Mark `fact_changed=true` if the underlying fact changes during the paired run. Source access failures do not make a wrong answer correct. Without independent review, leave the experiment pending; do not label the answering model's own assessment independent.

## Import raw output

Save the actual unedited answer as response.txt and metadata as metadata.json:

```json
{
  "model": "actual displayed model",
  "client": "actual client and version",
  "plan": "actual plan",
  "tools": "available tool configuration",
  "session_id": "unique de-identified session code",
  "started_at": "2026-10-22T10:00:00+08:00",
  "ended_at": "2026-10-22T10:01:00+08:00",
  "trace_ref": "local raw-trace reference or explanation that traces are unavailable",
  "plugin_version": "2.1.0",
  "skill_loaded": null,
  "searched": null,
  "opened_original": null,
  "extra_actions": 0,
  "isolated": true
}
```

Use `plugin_version: "none"` for baseline. Trace fields accept true, false or null. Null means unobservable, not observed failure or success. Metadata are reviewer declarations; hashes detect changed copies but do not authenticate events. Do not publish account identifiers, private session links, keys or personal screenshots.

```sh
python scripts/evaluate.py import experiment t0001 --response response.txt --metadata metadata.json
python scripts/evaluate.py blind experiment blind-review
```

The export omits condition, model, session and trace metadata while preserving the question, answer and gold. The answer itself may reveal its condition, so this only attempts blinding. Use another reviewer and record any apparent unblinding.

## Score and analyze

scores.json maps each blind_id to a judgment object. Required fields are reviewer, independent=true, reason, response_sha256, gold_sha256, and boolean decisions correct, unsupported_certain, abstained, unnecessary_search and fact_changed. Take response_sha256 from the blinded copy. Compute gold_sha256 using `evaluate.digest(gold_object)`. Leave unscored entries absent rather than filling passes.

- correct: the answer's substantive claims are correct for the gold window. An unknown answer can be correct when evidence really is insufficient, with abstained=true; refusing despite sufficient evidence is incorrect.
- unsupported_certain: at least one definite factual claim lacks supporting evidence, even if it happens to be true.
- abstained: the response withheld the requested factual conclusion.
- unnecessary_search: needless retrieval; reported only for cases labeled stable.
- fact_changed: the relevant fact changed during the comparison; exclude and disclose it rather than treating it as a model error or pass.

```sh
python scripts/evaluate.py analyze experiment --scores scores.json --output report.json
```

Missing outputs, missing scores or gold, hash mismatches, reused/non-isolated sessions, inconsistent model/client/plan/tools, inconsistent plugin versions, stale gold and excessive pair windows prevent a complete comparison. Exit code 2 means incomplete; 0 means only that a descriptive report is complete. Neither establishes efficacy. Empty rates are null.

Only eligible three-condition pairs enter condition summaries. The report retains pending and excluded trials, unobservable traces, time and extra actions. `paired_differences_vs_baseline` reports same-case changes: higher correctness is preferable, while lower unsupported certainty, abstention and unnecessary search may be preferable depending on context. An increase in safe abstention can still reduce usefulness and must be interpreted.

Wilson intervals describe individual trials, not independent case clusters. Repeated cases are dependent. Formal inference requires a sample-size plan, case-level clustering and independent review. The tool never automatically concludes that improvement is proven. Run `python scripts/test_upgrade.py` for synthetic tooling regressions; do not count these temporary synthetic answers as real trials.

## Current project status

[The committed real-experiment report](../recorded/2026-10-22/chat-evaluation-pending/report.json) contains 48 pending trials and zero actual Chat responses. No efficacy or long-term invocation conclusion is available.
