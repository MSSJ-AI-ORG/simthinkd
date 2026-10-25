# Router kit (0.4.0)

SimThink D in front of a large model: a fast path for what it knows, and a hand-over for the rest. This page covers the
design, the rules and the limits. The code is `src/simthinkd/router.py`, `relearn.py`, `adapters.py` and `dom_adapter.py`.

## Parts

```
observation ─► adapter ─► sentence ─► decider (about 2 ms) ─► state, confidence
                                                                 │
                         skill table: state -> (action, expected next states, final?)
                                                                 │
          p < tau ───────────────────────────────────────────────┼─► hand-over: low_confidence
          no skill for this state ───────────────────────────────┼─► hand-over: unknown_state
          not an expected next state of the last fast action ────┼─► hand-over: no_progress
                                                                 └─► fast action
every route ─► HandoffMonitor ─► fired ─► relearn: teacher labels → retrain → hot swap → log line
```

| Part | API | Job |
|---|---|---|
| Router | `Router(decider, skills, tau=0.9, adapter=None, monitor=None)` | one route per observation; `reset(expect=)` starts an episode |
| Route | `route.kind` (`action` / `handoff`), `action`, `reason`, `detail`, `state`, `confidence`, `expect`, `ms` | the answer |
| Skill table | `SkillTable({...})`, `SkillTable.from_transitions(...)`, `save` / `load` | per state: scripted action, expected next states, final |
| Monitor | `HandoffMonitor(window=10, rate=0.5, no_progress=3)` | relearning trigger |
| Relearn | `relearn(router, teacher, observations, base_examples, out=..., log=...)` | teacher labels, retraining, hot swap, log |
| Adapters | `ScreenAdapter`, `PipelineAdapter`, `VectorAdapter`, `DomAdapter`, `CombinedAdapter` | observation -> sentence |
| DOM check | `DomVerifier`, `VerifiedRouter(router, verifier)` | capture decides, DOM verifies; hand-over `verify_disagree` |

## Rules

1. The checks run in a fixed order: low confidence, then unknown state, then no progress. A route gets the first
   reason that applies.
2. After a fast action, the router remembers that action's expected next states. The next observation must show one of
   them. If it shows the same state again, `detail` is `same_state` (the action did nothing). If it shows another state,
   `detail` is `unexpected_state` (the action went somewhere else, or the screen was misread).
3. If a skill records no expectation (`expect=None`), the router only checks that the state changed. This was the rule
   of our first screen-router experiment. It misses a wrong action that leads to a different known state, so record
   expectations where you can.
4. A final skill ends the checks. `reset(expect=[...])` sets what the first observation of an episode must show. This
   catches a model that confidently claims "done" on the first screen of a site it has never seen.
5. After a hand-over nothing is expected, because the large model chose the action. If you know where its action should
   lead, call `router.expect([...])`.
6. Every handed-over observation is kept (up to `keep`, default 1000). `take_handed_over()` returns and clears them.
7. `relearn` refuses to run while the router's monitor has not fired, unless `force=True`. It builds the new training set
   from `base_examples` (what the current decider learned) plus the teacher's labels. It keeps at most 8 labels and
   trains with `simthinkd.fit` (or `trainer=`). Only then does it swap the decider. If training fails, the old decider
   stays. Each run appends one JSON line (`simthinkd-relearn/1`) to `log`.
8. `route()` and `swap()` share one lock, so routes in flight finish on the decider they started with. One router
   follows one episode at a time.

## Adapters

- `ScreenAdapter`: the screenshot is box-resized to 64 x 48 and cut into 8 x 6 cells. Each cell gives its mean colour
  class, and a saturated-colour token if at least 4 of its 64 pixels are saturated. The sentence also carries the window
  title and the previous action. For sizes that divide evenly (1024 x 768, 640 x 480, 256 x 192) this is the same
  feature as our screen-router experiment (`tests/test_router.py` checks it against the Pillow version). Other sizes use
  an area average that can differ in a few cells. One deliberate change: when two saturated colours tie, the one seen
  first in the cell wins. The experiment picked one at random.
- `PipelineAdapter`: `step`, the chosen request fields (sorted, or the order you give) and the gate name, verdict and
  first reasons. It is for routing inside a fixed pipeline: which step next, what a gate failure means, which model tier.
- `VectorAdapter`: the chosen entries of a numeric vector, each clipped to its range and put in one of `levels` bins.
  Missing or infinite values are refused.

## DOM input (dom_adapter.py)

The colour grid cannot tell two screens apart when they look the same but mean different things (the same green button
labelled "Submit request" on one screen and "Cancel request" on another). On a web page the DOM can.

- `DomAdapter`: a DOM snapshot -> `title: ... | path: /index.html | prev: ... | dom: button submit_request ; textbox username`.
  Only visible interactive elements (buttons, links, fields, ARIA roles), each as role + name, plus `disabled` and
  `covered` (another element sits on its centre, e.g. a banner or a dialog). What a person typed is never read; the URL
  keeps its path only. At most `max_elements` (32) elements of at most `max_name` (32) characters, in reading order.
  `DOM_SNAPSHOT_JS` collects the snapshot in a browser through the Chrome DevTools protocol (`Runtime.evaluate`).
- `CombinedAdapter`: the ScreenAdapter sentence followed by the DOM part (the union of both inputs).
- `DomVerifier` + `VerifiedRouter` (two steps: the screenshot decides, the DOM checks). The verifier learns, per state,
  the elements every training snapshot showed. The script author names the control each action presses. A fast action
  runs only if the decided state's elements are all there and the target control is present, enabled and not covered.
  Otherwise the route becomes a hand-over with reason `verify_disagree` (detail: `missing_elements`, `no_target`,
  `target_disabled`, `target_covered`, `target_moved` or `no_signature`). The wrapped router's monitor has already counted
  the route as a fast action. `VerifiedRouter.counts` holds the agreements and disagreements. `where(route, observation)`
  can give the target and the click point per route (for example the item a mission orders). With a point, the target
  must contain it, else `target_moved`: the layout shifted and the fixed click would press something else.
- `PopupGuard` (an unexpected popup): it looks at the topmost dialog in the snapshot (`role=dialog`, `alertdialog`,
  `<dialog>`, `aria-modal`). If every control there is a close control (닫기, X, close), a never-again control
  (다시 보지 않기, 오늘 하루 보지 않기) or an information link (자세히 보기), it names the close control to press. A
  never-again control is pressed only with `allow_never_again=True`. Any other control (pay, agree, extend, leave, OK)
  means the popup asks for a decision, so it is never closed automatically (`decision_needed`). After pressing, call
  `router.expect([...])` with the screen that should come back, so the next route checks it.
- The DOM is only available for web pages (and apps that expose an accessibility tree). For desktop programs, games and
  robots the capture route stays the only one.

## Limits

- The router is only as good as the decider on the states it has learned. A screen it has never seen can still be
  accepted with high confidence. The no-progress check catches this one step later, after one wrong action. Use it for
  actions that are harmless to repeat or undo, and keep irreversible actions (sending, paying, deleting) behind the
  large model or a person.
- The example uses a synthetic app that we built and stub models. It shows that the logic works as designed. It does
  not measure a real website, a real large model, or a robot.
- `relearn` does not check the teacher. Wrong teacher labels become wrong training data.
- A decider holds at most 8 states, so one router covers one fixed task, not a whole application.

## Reproduce and preregister

`examples/router_screen` contains `PREREG_TEMPLATE.json` and `seal_prereg.py`. Fill the template, run a pilot on pilot
seeds only, then seal the plan before the test runs. Sealing records the hashes of the frozen code and of the plan
itself. `verify` checks that nothing changed. `tests/test_router_example.py` verifies the example's seal, runs it twice
and checks that the digest is the same both times.
