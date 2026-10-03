# Changelog

## 0.2.0 - 2026-10-03

- Score models: `simthinkd.fit_score` and `Scorer` return one number (a risk level, a priority) instead of an action. Training is on the CPU; scoring needs only NumPy.
- `examples/risk_score.py`: a 0 to 100 risk score for parts on an inspection belt.
- README: "Where it fits", including two ways to use SimThink D with a large model (first filter, local backup), and where it is not a good fit.
- `tests/test_score.py` runs in CI.

## 0.1.0 - 2026-10-03

First public release.

- Python package with two Doom deciders (`doom-defend`, `doom-corridor`).
- `simthinkd` command line: `decide`, `serve`, `bench`, `train`, `list`.
- Train your own decider from a rule teacher with `simthinkd.fit`.
- Browser version in plain JavaScript, Gradio demo, Colab notebook.
- MCP server and LangChain tool.
