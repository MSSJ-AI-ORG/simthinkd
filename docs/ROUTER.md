# Router kit (0.4.0)

SimThink D in front of a large model: a fast path for what it knows, and a hand-over for the rest. This page covers the
design, the rules and the limits. The code is `src/simthinkd/router.py`, `relearn.py` and `adapters.py`.

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
| Adapters | `ScreenAdapter`, `PipelineAdapter`, `VectorAdapter` | observation -> sentence |

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
