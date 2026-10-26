# Synthetic screen benchmark

Two local apps: a seeded HR ERP and an image studio returning local placeholder
images. All people, records and transactions are synthetic. No paid image API,
real site, login, or purchase is used. The app files are unchanged from v30.

Install the package from the repository root and the benchmark dependencies:

```sh
python -m pip install -e '.[train]' pillow websocket-client pytest
cd benchmarks/screen
python run.py --app erp --cond decider --seed 502 --reps 3 --out runs/erp
python run.py --app img --cond decider --seed 601 --reps 3 --out runs/img --llm-cmd '["python", "bridge_codex.py"]'
python run.py --app erp --cond llm --seed 502 --reps 3 --out runs/llm --llm-cmd '["python", "bridge_codex.py"]'
python -m pytest -q test_bench_offline.py
```

Chrome is discovered on Windows/Linux/macOS; override with `--chrome PATH`.
The runner starts its own headless Chrome profile and loopback HTTP/CDP servers.
Use a fresh output directory for each invocation. Training uses seeds 1001–1060;
test seeds must not overlap. `--train-seeds N` is a pilot override, not the v30
training protocol. Teacher collection and training occur before mission timing.
The normal ERP mission needs no large model. Any unhandled state fails honestly
with `HANDOFF_REQUIRED` if no model command is configured. The image mission's
decision-bearing credit popup needs a model bridge. It is never silently answered
by the scoring oracle.

The bridge command receives one JSON object on stdin: `schema`, `screenshot`
(a local PNG filename), `mission`, `previous`, and `actions`. Return only one JSON
object on stdout: `{"action":"PRESS","label":"Continue"}`, or TYPE with `label`
and `text`, or `{"action":"WAIT"}` / `{"action":"DONE"}`. `bridge_codex.py` is a working example that calls
the Codex CLI the way our v30 runs did and translates its answer. The runner does not assume a
particular CLI's flags or output. On Windows, a JSON argv array avoids quoting
ambiguity. Commands run without a shell and have a 180-second timeout. Missing
`--llm-cmd` skips the llm condition, writes a skip summary, and never starts Chrome.

`timings/` contains per-run JSON with elapsed seconds, success, model calls,
decisions, actions and oracle scoring. `SUMMARY.json` aggregates only this
invocation. Timing, platform and screenshots are measurements and are not
byte-reproducible. The offline test checks deterministic plans, scoring, and a
summary made from fixed measurement inputs; it does not claim identical live
timings. `data/` and `models/` retain teacher rows and trained models.

## Historical v30 results, not results of this port

On a separate Linux workstation, v30 reported three runs per condition:

| Synthetic app | LLM alone mean | SimThink D + LLM mean | Mean model calls, alone / routed |
|---|---:|---:|---:|
| HR ERP | 143.5 s | 7.3 s | 14 / 0 |
| Image studio | 125.5 s | 20.4 s | 14 / 1 |

All four groups succeeded 3/3. Source: the v30 experiment's `REPORT_v0.1.md`
(2026-10-25), generated from its timing JSON. These are historical measurements,
not independently rerun results from this port or a guarantee on other machines.
Fixed layouts, one mission per app, one popup type and three repetitions limit
generalization. The classifier can be confidently wrong on unseen screens; DOM
verification and popup handling are essential. There is no real-site performance
claim. See `PORT_NOTES.md` for the checks actually run on this port.
