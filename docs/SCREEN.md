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

On a synthetic HR ERP (our own test app, fixed layout, synthetic data), a large model alone took 143.5 s per mission on
average with 14 large-model calls; with SimThink D in front it took 7.3 s with 0 calls (3 of 3 runs each). On a live
shopping site (code not published), the guards on this page took one mission from 80.8 s to 29.2 s on average, 12 of
12 runs succeeded. The benchmark in `benchmarks/screen` reruns the synthetic part; see [REPRODUCE.md](REPRODUCE.md).

## Limits

- It is fast on screens it has learned. An unseen screen goes to the DOM check or the large model.
- A screenshot-only decider read an unseen popup as a known screen with high confidence (0 of 3 on our image-site
  app); use the DOM check.
- Site values (bands, link filters, success words) are the caller's. Nothing here is tuned to one site.
