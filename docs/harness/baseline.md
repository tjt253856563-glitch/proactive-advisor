# Baseline audit

The development branch starts at `142b51e68e9076af71ceb6ef8d8e43f820594d96`. The `v1.2-candidate` tag points to `4d2e807`. On main the active rules are in `skills/proactive-advisor/SKILL.md`. No root AGENTS.md or PLAN.md was tracked. The context-followthrough experiment has its own plan and copies of historical rules. Freshness Guard and the Chat pilot have separate histories, with PR refs #2 and #3.

| Component | Verified behavior on the starting revision | Coverage gap |
| --- | --- | --- |
| Skill | Four levels, all six labels, intent retention, suggestion filtering and a bounded goal loop are present as instructions | The instructions specify behavior but have no execution or state machinery |
| `goal_check.py` | Writes locally supplied status and evidence to a JSON ledger | No tests run and no evidence authenticity checks |
| `scripts/install.py` | Existing tests cover installation, collisions and protected uninstall | Installs the behavior rules only |
| `evals/run.py` | Paired fixture setup, real adapter subprocesses, snapshots, diffs and blind rating packets | Human ratings and configuration/skill-loading audits remain separate. No goal runtime, repair or checkpointed execution |
| Existing model observations | Published small historical replay with no established general advantage | No stable relative effect, live goal loop or verified cross-session loading |
| Other experiments | Sources and records exist on their own paths and branches | Their scores do not measure this runtime |

On Linux/Python 3.12, `python -m unittest discover -s tests -v` passed 15/15 on the clean starting revision. `evals/run.py prepare` created 48 development trials using the environment template. `report` correctly classified all 48 as NOT_RUN because no model ran. Existing code and experiment histories are retained.
