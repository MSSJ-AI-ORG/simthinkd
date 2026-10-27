# Screen control (0.5.0)

How to put SimThink D in front of a large model on a screen task, and which guards make it fast and safe. The router
itself is described in [ROUTER.md](ROUTER.md); this page is the practical manual for screens.

## The loop

```
screen ─► capture (+ DOM snapshot) ─► Router: state, confidence ─► VerifiedRouter: DOM agrees? ─► RuleFirst / skill
   ▲                                                                    │ no                         │
   │                                                                    ▼                            ▼
   │                                                        hand over to the large model     open_or_press + NoClickBands
   │                                                                                                 │
   └──────────────────────────── ExpectAfter: expected screen in time? ─── no ─► undo own action, hand over
                                                     │ yes
                                                     ▼
                                       PageTextCheck: done? ─► stop
```

## Guards

| Guard | What it stops | Give it |
|---|---|---|
| `DomVerifier` / `VerifiedRouter` | a screenshot read wrongly with high confidence (an unseen popup looked like a known screen) | per-state element signatures (learned) and per-action targets |
| `PopupGuard` | a popup that asks for a decision being closed automatically | nothing; optional extra close / never-again words |
| `NoClickBands` | a click landing on a fixed header or footer that covers the page | band heights of the site |
| `open_or_press` | waiting for a card click to open a new tab | an `allow(href)` filter for the site |
| `ExpectAfter` | a step that silently went nowhere | a state reader, timeout |
| `RuleFirst` | asking the decider where a rule is certain | (predicate, action) pairs |
| `PageTextCheck` | declaring success from a screenshot | success words or a counter |

## What we measured

On a synthetic HR ERP (our own test app, fixed layout, synthetic data), a large model alone took 118.3 s per mission on
average with 14 large-model calls; with SimThink D in front it took 7.2 s with 0 calls (3 of 3 runs each, local
headless Chrome, sealed before measuring). On a synthetic image studio, a large model alone took 126.6 s (14 calls each); with SimThink D in front it took 24.3 s with 1 or 2 calls, because the decision-bearing credits popup always goes to the large model (3 of 3 runs each). In our first sealed run one of these missions failed; the cause was in the benchmark runner and is fixed (see CHANGELOG). On a live
shopping site (code not published), the guards on this page took one mission from 80.8 s to 29.2 s on average (three runs for each
of the four steps, 12 of 12 succeeded). The benchmark in `benchmarks/screen` reruns the synthetic part; see [REPRODUCE.md](REPRODUCE.md).

## Limits

- It is fast on screens it has learned. A screen goes to the large model only when the decider is unsure, the DOM
  check disagrees, a step made no progress, or a popup asks for a decision. An unseen screen that looks like a known
  one, with the same page elements, can still be accepted wrongly, and an unfamiliar popup with only close controls
  is closed locally.
- A screenshot-only decider read an unseen popup as a known screen with high confidence (0 of 3 on our image-site
  app); use the DOM check.
- A screen caught halfway through a change (results appearing while generation ends) can get a low confidence and be
  handed to the large model, which costs one extra call (about 9 s in our image-studio runs). Waiting first would be
  cheaper; we have not measured that yet.
- Site values (bands, link filters, success words) are the caller's. Nothing here is tuned to one site.
