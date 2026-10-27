# Changelog

## 0.5.0 - 2026-10-27

- Screen actions (`src/simthinkd/screen_actions.py`, new module): general forms of the guards that cut one live screen-control mission from 80.8 s to 29.2 s on average (three runs for each of the four steps, 12 of 12 succeeded; the site code is not published). `NoClickBands` keeps clicks out of fixed header and footer bands that the accessibility tree misses. `open_or_press` opens a plain http(s) link by its address instead of clicking its card. `ExpectAfter` waits for one of the expected screens after an action and reports a miss. `RuleFirst` uses a known rule before asking the decider, and a rule that raises never blocks the fallback. `PageTextCheck` judges success from page text or a counter that grew. Every site value is passed in by the caller. Tests: `tests/test_screen_actions.py`.
- Screen benchmark (`benchmarks/screen`, new): two synthetic apps (an HR ERP and an image studio) in local headless Chrome, a runner with sealed seeds, and one command to plug in a large model (`bridge_codex.py` is an example). In our first sealed run one image-studio mission failed: the large model answered "Download #2", the page pressed "Download image 2", and the runner did not map that press to the decider's own action name, so the decider downloaded the same image again. The runner now maps a large-model press by the control actually pressed (`engine.canon_of`), with a test.
- Fixes from an external review before release: `PopupGuard` now counts a decision control even when it is partly covered (a covered Pay button next to a Close button used to let the popup be closed); `DOM_SNAPSHOT_JS` no longer reads the text of an editable element (typed text could become an element name); `relearn` checks the new skills before it swaps the model, so a failed call changes nothing; the benchmark checks the control a model press resolves to, not only the model's word ("credits" could resolve to "Buy credits"); CI installs the benchmark's test dependencies. Each has a test.
- Docs: `docs/SCREEN.md` (manual), a screen section in the README and on the project page, and the bench commands in `docs/REPRODUCE.md`.
- This release also carries everything listed under 0.4.0 below; 0.4.0 was not published on its own.
- No change to the 0.3.0 API.

## 0.4.0 - not published on its own (in 0.5.0)

- Router kit. `Router` + `SkillTable`: SimThink D names the state, the skill table gives the scripted action, and the router hands the case over (to a large model or a person) for one of three reasons: `low_confidence`, `unknown_state`, `no_progress`. The no-progress check compares the observed state with the expected next states of the last fast action, so a confident wrong action is caught at the next observation. `SkillTable.from_transitions` learns the expected next states from teacher runs. `Router.reset(expect=...)` checks the first state of an episode too.
- `HandoffMonitor`: relearning trigger over the last 10 routes (hand-over rate 0.5, or 3 no-progress hand-overs).
- `relearn`: teacher labels, retraining, hot swap of the decider in a running router, and a JSON-lines log. It refuses to run before the monitor fires unless `force=True`.
- Feature adapters: `ScreenAdapter` (colour grid of a screenshot + window title + previous action), `PipelineAdapter` (request fields + gate verdict), `VectorAdapter` (quantised part of an observation vector).
- `examples/router_screen`: the router logic on a small synthetic screen task, with no network and a stub large model. It includes a sealed preregistration (`seal_prereg.py`, `PREREG_TEMPLATE.json`) and the sealed results.
- Tests: `tests/test_router.py` (NumPy only) and `tests/test_router_example.py` (runs the example twice and checks that the digest is the same).
- DOM input (`src/simthinkd/dom_adapter.py`, new module; router.py, relearn.py and adapters.py are unchanged): `DomAdapter` turns a compact DOM snapshot (visible interactive elements: role, accessible name or text, enabled, covered; page title and URL path) into the same sentence form the decider reads. It never reads what a person typed, drops the URL query, bounds the length and sorts the elements in reading order. `CombinedAdapter` puts the screenshot grid and the DOM part in one sentence. `DomVerifier` + `VerifiedRouter`: the screenshot decides, the DOM checks (the state's learned element signature, and that the target control exists, is enabled and is not covered); on a disagreement the case is handed over with reason `verify_disagree`. `DomVerifier.verify` also takes a per-call target and click point (`target_moved` when the layout shifted). `PopupGuard` decides from the DOM whether an unexpected popup may be closed without the large model: only when its topmost dialog has nothing but close, never-again or information controls; a popup that asks for a decision (pay, agree, extend, leave) is never closed automatically. `DOM_SNAPSHOT_JS` collects a snapshot through the Chrome DevTools protocol, with the dialog each element belongs to. Tests: `tests/test_dom_adapter.py`.
- No change to the 0.3.0 API. Existing deciders and score models load and answer as before.

## 0.3.0 - 2026-10-05

- Many decisions at once: `Decider.ask` answers several questions about one situation in one call (choice, score from 1 to 10 levels, true/false); each question is pooled on its own, so adding a question never changes another answer. `Decider.predict_batch` and `ask_batch` run many requests through the network in one pass and return the same answers as one at a time. See docs/PARALLEL.md.
- `simthinkd bench --batch`: decisions per second one at a time and in batches, and the share of time spent encoding text, running the network and building answers. On our machine encoding is most of the time, so batching speeds up the network but not yet the whole call.
- Server: inference is serialised inside one process (a lock); a threaded server under heavy parallel load could crash in the BLAS library. Run several server processes for more throughput.
- Java runtime (`java/`): the same model in plain Java 8 inside your process, with `tools/export_java_weights.py`; `tests/test_java_parity.py` checks that it chooses exactly what Python chooses.
- README in Korean and Japanese, and a language switch on the project page.

## 0.2.1 - 2026-10-04

- Server: answers on a kept-alive connection took about 40 ms because headers and body go out as two small writes (Nagle's algorithm plus delayed ACK). `simthinkd serve` now sets TCP_NODELAY on every connection. Measured on Linux: median 42 ms before, 1.4 ms after, for clients that reuse connections (for example Java `HttpURLConnection`).
- `tests/test_server_latency.py` checks that a kept-alive request answers in under 20 ms.

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
