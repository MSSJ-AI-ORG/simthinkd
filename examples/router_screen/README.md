# Screen router (router kit example)

SimThink D in front of a large model on a fixed screen task. It recognises the screen in about 2 ms and does the
scripted action. When it is unsure, when the screen is not part of the task, or when the last fast action did not lead
to an expected next screen, it hands over to the large model. When it hands over too often (a site redesign), a teacher
labels the new screens, the decider is retrained in seconds and swapped in.

This is the logic of our experiments v2.1 (screen router) and v2.2 (local variations and relearning), rebuilt on a small
synthetic app. It needs no browser and no network. The "large model" and the teacher are stubs that read the app's true
state; each hand-over is counted as one model call.

## Run

```bash
pip install "simthinkd[train]"
python seal_prereg.py verify PREREG_router_screen.json   # the plan was sealed before the run
python run.py --out out                                  # about a minute on a CPU
```

`out/result.json` holds every count, and `out/relearn.jsonl` holds the relearning log. Our sealed run is in
[RESULTS_router_screen_v1.json](RESULTS_router_screen_v1.json).

## What our sealed run measured

| Phase | Runs | Success | Hand-overs | Notes |
|---|---|---|---|---|
| Learned screens, no disturbance | 12 | 12 | 0 of 64 routes | every action on the fast path |
| Notice banner (never trained) | 4 | 4 | 4 no-progress | the save did nothing; caught at the next screen |
| Session page (never trained) | 4 | 4 | 4 low-confidence | |
| Wrong expectation planted | 12 | 12 | 26 no-progress | the table was wrong; nothing was silently accepted |
| Wrong action planted | 12 | 12 | 12 no-progress | 12 of 12 wrong actions caught at the next screen |
| Redesign, before relearning | 10 | 10 | 41 of 58 routes (35 low-confidence, 6 no-progress) | trigger fired at route 10 |
| Redesign, after relearning | 18 | 18 | 0 of 96 routes | 101 teacher labels, 3.7 s training |
| Old layout after relearning | 10 | 10 | 0 of 54 routes | nothing forgotten |

All eight sealed hypotheses held. A second run gave the same digest. This is a small synthetic app that we built
ourselves, so these numbers show that the kit reproduces the experiment logic. They do not show how it works on a real
website.

## Files

| File | What it is |
|---|---|
| `screens.py` | the synthetic app: two layouts, local variation, banner and session disturbances |
| `run.py` | teach, train, route, negative controls, redesign, relearn, recheck |
| `PREREG_TEMPLATE.json` | an empty preregistration to copy for your own experiment |
| `PREREG_router_screen.json` + `.sha256` | the sealed plan of this example (seeds, thresholds, hypotheses, frozen code hashes) |
| `seal_prereg.py` | `seal` a plan before running, `verify` it afterwards |
| `RESULTS_router_screen_v1.json` | our sealed run, with a verdict per hypothesis |

The PREREG freezes `run.py`, `screens.py` and the router kit source files. If you change one of them, `verify` fails.
Write a new PREREG (`..._v2`) and seal it, instead of editing the sealed one.
