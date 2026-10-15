# Proactive Advisor — experimental

[中文](README.md) · [Installation / uninstall](docs/installation.md) · [Evaluation protocol](evals/README.md) · [Report a failure](https://github.com/tjt253856563-glitch/proactive-advisor/issues/new/choose)

Behavior guidance intended to help an AI assistant retain the current user goal, complete authorized changes, avoid unnecessary edits, and distinguish evidence from completion claims. It is a readable skill, not an agent runtime, permission system or background service. The current skill instructions are in Chinese; the English documentation does not imply an English-language behavioral validation.

**A general improvement over an unassisted baseline has not been established.** Six pilot baseline/v1.1 pairs and two v1.1/v1.2-candidate pairs produced largely similar behavior. One loaded-skill edit expanded the requested scope; it was not a consistently reproduced defect. The evaluation was small, unblinded and lacked independent full trace verification. The v1.2 skill remains a candidate.

## Try it

Requires Python 3.10+ for the optional installer:

```sh
git clone https://github.com/tjt253856563-glitch/proactive-advisor.git
cd proactive-advisor
python scripts/install.py install --project "/absolute/path/to/your/project"
```

Open a new Codex chat in the target project and ask it to use `$proactive-advisor` for a concrete task. Check the actual skill-file read and resulting artifacts. Copy/uninstall behavior has been tested locally on Windows; client discovery, automatic invocation, ChatGPT Work and cross-client behavior require separate checks. See [installation details](docs/installation.md) for collision protection, manual copying and uninstalling.

## Reproduce and contribute

New: [context follow-through experiment](experiments/context-followthrough/README.md), with a focused candidate skill, three reconstructed/synthetic scenarios, a runnable harness, and nine actual responses. All three conditions passed maintainer review; no incremental benefit was observed. The original Work failure was not fully recovered or reproduced. The candidate is not behavior-validated and does not replace the default installed skill.

The evaluation corpus contains eight reconstructed historical tasks and two synthetic reserved cases. These are **not ten independently collected real-user failures**. The stdlib harness creates separate paired workspaces, randomizes order, captures adapter output and file changes, and exports anonymous review packages. Mechanical checks, runtime errors and human behavioral ratings are reported separately. It never turns a successful process exit into a claim that the skill works.

See [the protocol](evals/README.md) to prepare and run your own experiment. Adapter execution can consume model quota and uses the configured client's permissions. The included Codex command is a starting template; no new live model evaluation is claimed for this tooling update.

```sh
python -m unittest discover -s tests -v
```

These tests verify the installer and harness, **not model quality**. The `goal_check.py` helper separately records user-supplied results and does not execute checks or authenticate evidence.

Fifteen local infrastructure tests pass. The GitHub CI workflow covers Windows/Linux and Python 3.10/3.12. Check [Actions](https://github.com/tjt253856563-glitch/proactive-advisor/actions/workflows/checks.yml) for the result of a specific commit; see [CI scope](docs/ci.md) for what these checks establish.

Useful feedback includes the redacted task, client/model/settings, both baseline and skill outputs, actual file differences and unwanted side effects. [Contribution guide](CONTRIBUTING.md). We do not claim external adoption from stars, downloads or infrastructure checks.

## License

MIT. See [LICENSE](LICENSE).
