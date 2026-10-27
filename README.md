<p align="center"><b>English</b> | <a href="README.ko.md">한국어</a> | <a href="README.ja.md">日本語</a></p>

<p align="center"><img src="assets/banner_v2.png" alt="SimThink D: a local backup for cloud decisions" width="100%"></p>

<p align="center">
  <a href="https://pypi.org/project/simthinkd/"><img src="https://img.shields.io/pypi/v/simthinkd" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License: Apache 2.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <a href="https://github.com/MSSJ-AI-ORG/simthinkd/actions/workflows/test.yml"><img src="https://github.com/MSSJ-AI-ORG/simthinkd/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://colab.research.google.com/github/MSSJ-AI-ORG/simthinkd/blob/main/notebooks/quickstart.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open in Colab"></a>
  <a href="https://arxiv.org/abs/2610.04810"><img src="https://img.shields.io/badge/arXiv-2610.04810-b31b1b.svg" alt="arXiv:2610.04810"></a>
</p>

<p align="center"><b>Network down. Decisions stay local.</b></p>

SimThink D is a small CPU model for offline backup decisions.
It has 265,665 parameters and takes about 2 ms per decision on one CPU core.

In the factory simulation, the internet was cut for 15 seconds.
The local backup got 59 of 63 parts right, with no late decisions.

<p align="center"><a href="assets/factory_fallback.mp4"><img src="assets/factory_twin.gif" alt="Factory simulation: the internet is cut for 15 seconds and SimThink D on the factory PC fills the gap" width="100%"></a></p>

<p align="center"><a href="https://mssj-ai-org.github.io/simthinkd/">Project page</a> · <a href="https://mssj-ai-org.github.io/simthinkd/#demo">Try in your browser</a> · <a href="assets/factory_fallback.mp4">Watch the video (72 s)</a> · <a href="examples/factory_twin/">Factory code</a> · <a href="docs/PAPER.md">Paper</a></p>

```bash
pip install simthinkd
```

What makes the next decision when your network goes down?

## Words used here

- **Tick**: one step of a game or control loop. Doom runs at 35 ticks per second, so one tick is 28.6 ms.
- **Decider**: the small model. It gets a short sentence about the situation and returns one action.
- **Teacher**: your own rules, written as a normal function. The decider learns by copying the teacher.
- **Perception**: your code that turns the raw game state into the short sentence.

## Install

```bash
pip install simthinkd
```

That is all you need to make decisions. It only needs NumPy. To train your own decider, add the `train` extra (it adds PyTorch, CPU build is fine):

```bash
pip install "simthinkd[train]"
```

## Quickstart

```python
from simthinkd import Decider

d = Decider("doom-defend")
print(d.decide("seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25"))
# TURN_LEFT (100%, 1.1 ms)
```

One call is one decision. A short sentence goes in. One action comes out, with its probability and the time it took. The first call also loads the model, so it is slower. After that, a call takes about 1 ms.

Two deciders come with the package: `doom-defend` (stand in the middle and fight) and `doom-corridor` (fight your way down a corridor).

## Many decisions at once

One call can carry several questions about the same situation, and one batch can carry many situations. The answers are the same as asking one by one.

```python
from simthinkd import Decider

d = Decider("doom-defend")
states = ["seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25",
          "seen: Demon right a30 d5 | enemies 1 | sway right | gun ready | ammo25"]
answers = d.predict_batch([d.request(s) for s in states])   # many situations in one pass
print([a["operation"]["choice"] for a in answers])
# ['TURN_LEFT', 'TURN_RIGHT']
```

`simthinkd bench --batch` shows where the time goes on your machine. Details and limits: [docs/PARALLEL.md](docs/PARALLEL.md).

## Train your own in seconds

A new task needs two things: a perception step and a teacher. The `toy` module below is a small made-up task, an inspection station on a factory belt. Swap its examples and actions for your own.

```python
import simthinkd
from simthinkd import toy

d = simthinkd.fit(toy.examples(3000), toy.ACTIONS, goal=toy.GOAL, out="inspection")
print(d.decide("part: defect dent | severity severe | image clear | belt normal | rework queue long"))
# REJECT (100%, 1.2 ms)
```

On our test PC this trains on the CPU in about 8 seconds. The new decider then matched the teacher on 500 of 500 states it had not seen.

## Score instead of choose

Sometimes you need a number, not an action: a risk level, a priority, an expected wait. `fit_score` trains the same small network to return one number. Give it (situation sentence, number) pairs.

```python
import random
import simthinkd
from simthinkd import toy

SEVERITY = {"minor": 20, "moderate": 45, "severe": 75}

def risk(s):  # your own rule or records give the number
    value = 0 if s["defect"] == "none" else SEVERITY[s["severity"]]
    value += 10 if s["image"] == "blurry" else 0
    value += 8 if s["belt"] == "fast" else 0
    value += 5 if s["defect"] != "none" and s["queue"] == "long" else 0
    return float(min(100, value))

rng = random.Random(7)
examples = [(text, risk(state)) for state, text in (toy.observe(rng) for _ in range(3000))]
s = simthinkd.fit_score(examples, goal="Rate how risky this part is, 0 to 100.", out="risk", low=0, high=100, quiet=True)
print(s.score("part: defect dent | severity severe | image clear | belt fast | rework queue long"))
# 87.99 (0.22 ms)
```

The full script is [examples/risk_score.py](examples/risk_score.py). On our test PC, a risk score trained this way was off by 0.13 points on average (on a 0 to 100 scale) for 400 parts it had not seen. It put every pair of parts in the right order.

## Where it fits

SimThink D is a good fit when all three are true:

1. **The situation fits in one short line.** A few fields, like "seen: Demon left a30 d5 | enemies 1". Not a long text.
2. **The answer is small.** One of up to 8 actions, or one number.
3. **The answer must be fast, cheap or offline.** Every game tick, every part on a line, every control step, or when the network is down.

| Use | Why it fits | Try it here |
|---|---|---|
| Game characters | One decision every tick, 35 ticks a second | The two Doom deciders, `simthinkd bench` |
| Backup decider on a factory PC | Decides when a cloud service is late or offline | [examples/factory_twin](examples/factory_twin/) |
| Risk or priority score | One number per item, in well under a millisecond | [examples/risk_score.py](examples/risk_score.py) |
| A rule you already have | Learns your rule from examples, then runs it in about 2 ms | [Train your own](#train-your-own-in-seconds) |

### Use it together with a large model

Most of the time SimThink D works best as one part of a bigger system, not alone. Two patterns:

| Pattern | How it works | Try it here |
|---|---|---|
| **First filter** | SimThink D answers every case first. When it is not sure (its confidence is below a threshold you set), the case goes to a large model or a person. Easy cases stay cheap and fast; hard cases still get the big model. | `python examples/factory_twin/run.py --arm CASCADE --tau 0.9` |
| **Local backup** | A large model or cloud service answers first. When its answer is late or the network fails, SimThink D on the local machine answers instead. | The factory video above and [examples/factory_twin](examples/factory_twin/) |

A game character (NPC) is a natural first-filter case: SimThink D handles the moment-to-moment moves on every tick, and a large model is asked only for rare, slower choices such as planning or dialogue.

It is not a good fit for:

- **Judging long text** such as essays or reports. In our own test on essay sections, a simple word-count model did better.
- **Answers that are not in the line you give it.** If the answer depends on history the line does not contain, add that history to the line or use a different tool.
- **Open-ended answers.** It picks from a list or returns one number. It does not write.

## Route between a fast path and a large model

New in 0.4.0 (router kit). A `Router` puts SimThink D in front of a large model. The decider names the current state, a
skill table gives the scripted action for that state, and the router either does that action or hands the case over.

```python
from simthinkd import Decider, Router, SkillTable, ScreenAdapter

skills = SkillTable({"LOGIN":   ("FILL_LOGIN", ["PROFILE"]),        # state: (action, expected next states)
                     "PROFILE": ("SUBMIT", ["ERROR", "DONE"]),
                     "ERROR":   ("CLOSE", ["PROFILE"]),
                     "DONE":    ("STOP", None, True)})               # final: the task ends here
router = Router(Decider("models/screen"), skills, tau=0.9, adapter=ScreenAdapter())
router.reset(expect=["LOGIN"])
route = router.route({"pixels": screenshot, "title": "Sign in", "prev": None})
if route.handoff:
    action = ask_large_model(screenshot)     # route.reason says why
else:
    action = route.action                    # about 2 ms
```

A route is a hand-over for one of three reasons:

| Reason | When |
|---|---|
| `low_confidence` | the decider's confidence is below `tau` |
| `unknown_state` | the state has no skill in this table |
| `no_progress` | the state is not one the last fast action was expected to lead to |

The third check matters most. A small model can be sure and wrong on a screen it has never seen. If its action then
leads somewhere unexpected, or changes nothing, the very next route hands the case over. `SkillTable.from_transitions`
learns the expected next states from runs of your teacher.

- `HandoffMonitor()` watches the last 10 routes. It fires when half of them were hand-overs, or when 3 were no-progress.
- `relearn(router, teacher, observations, base_examples)` asks your teacher (a large model or a person) about those
  cases. It then retrains the decider, swaps it into the running router and appends one line to a log.
- Adapters turn different inputs into the decider's sentence: `ScreenAdapter` (a colour grid of a screenshot, the window
  title and the previous action), `PipelineAdapter` (request fields and a gate verdict) and `VectorAdapter` (part of a
  robot's observation vector). The decider stays the same; only the input changes.

[examples/router_screen](examples/router_screen/) runs all of this on a small synthetic screen task, with no network.
It includes a sealed preregistration and a template for your own experiments. In our sealed run, 12 of 12 deliberately
wrong actions were caught at the next screen. After a redesign, 101 teacher labels and 3.7 s of training brought the
hand-over rate from 41 of 58 routes back to 0 of 96. Details: [docs/ROUTER.md](docs/ROUTER.md).

## Drive a screen

New in 0.5.0 (screen kit). Guards for putting the router on a real screen, where a wrong click costs time or cannot be
undone.

```python
from simthinkd import NoClickBands, open_or_press, ExpectAfter, RuleFirst, PageTextCheck

bands = NoClickBands(top=96, bottom_from=700)            # fixed header and footer of the site
kind, where = open_or_press(element, allow=lambda href: "/item/" in href)
if kind == "open":
    browser.goto(where)                                    # a link: open it, do not wait for a click
elif bands.allows(where):
    browser.click(*where)
ok, state, ms = ExpectAfter(read_state, timeout=5.0).wait({"CART"})
if not ok:
    action = ask_large_model(screenshot)                   # the step went nowhere: hand over
```

- `NoClickBands` keeps clicks off fixed headers and footers that cover the page.
- `open_or_press` opens a link by its address instead of clicking a card and waiting for a new tab.
- `ExpectAfter` checks that the expected screen appears in time after an action.
- `RuleFirst` uses a rule where one is certain and asks the decider only where it is not.
- `PageTextCheck` decides success from the page text, not from a screenshot.
- `DomVerifier` and `PopupGuard` (also in this release) check the page structure before a confident fast action, and
  never close a popup that asks for a decision.

On our synthetic HR ERP, a large model alone took 118.3 s per mission on average (14 large-model calls each); with
SimThink D in front it took 7.2 s with 0 calls (3 of 3 runs each, local headless Chrome). On a synthetic image studio, a large model alone took 126.6 s (14 calls each); with SimThink D in front it took 24.3 s with 1 or 2 calls, because the decision-bearing credits popup always goes to the large model (3 of 3 runs each). In our first sealed run one of these missions failed; the cause was in the benchmark runner and is fixed (see CHANGELOG).
`benchmarks/screen` reruns both apps; a large model is plugged in through one command. Manual:
[docs/SCREEN.md](docs/SCREEN.md).

## Measure your own model

Does your model fit inside one tick? `simthinkd bench` replays 1,050 recorded Doom states that ship with the package. It times every decision, one request at a time.

```bash
simthinkd bench
simthinkd bench --url http://127.0.0.1:8000/v1/systemone --name my-model --tick-hz 35
```

The second line measures any server that accepts the [decision request](docs/PROTOCOL.md).

## Same CPU, same states

<p align="center">
  <img src="assets/side_by_side.gif" alt="Same Doom game, same seed, same CPU. Left: SimThink D answers every tick. Right: a 421M-parameter general decision model, used as published, misses most ticks while it thinks." width="100%" />
</p>

<p align="center"><sub>Same game, same seed, same 6-core CPU. Left: SimThink D, 1.9 ms per decision, 1 of 420 ticks missed. Right: Laya, a 421M-parameter open decision model, used as published without training on this game. It takes about 360 ms per decision and misses 390 of 420 ticks. A dark frame means the game moved on before the decider answered.</sub></p>

**Read this first.** Laya is a general model and was not trained on this game. Its published speed, about 33 ms per question, is on a GPU. We only had a CPU. So this table compares time inside a real-time loop. It does not compare overall quality.

We used one workstation CPU (6 threads) and 1,050 Doom states, then 10 live games on the same seeds. "Missed ticks" are ticks that passed before the decider answered.

| Decider | Parameters | Median decision time | Decisions within one 28.6 ms tick | Missed ticks in live play |
|---|---|---|---|---|
| SimThink D | 265,665 | 1.8 ms | 100% | 0.1% |
| Laya, as published | about 421M | 365 ms | 0% | 84.2% |

SimThink D only knows what its teacher knows. It does not reason, read long text or handle new actions without training. To run this comparison yourself, see [benchmarks/](benchmarks/).

## Use it from your stack

| Where | How |
|---|---|
| Any language, any engine | `simthinkd serve doom-defend --port 11890`, then POST the [decision request](docs/PROTOCOL.md) to `/v1/systemone` |
| Unity / C# | [docs/INTEGRATION_UNITY.md](docs/INTEGRATION_UNITY.md): a client loop that keeps the game running while it waits |
| Browser | [web/](web/): the same model in plain JavaScript, no server |
| Java / JVM games and engines | [java/](java/): the same model in plain Java 8, inside your process; export weights with `tools/export_java_weights.py`; a test checks it chooses exactly what Python chooses |
| A factory line (simulator) | [examples/factory_twin/](examples/factory_twin/): an inspection conveyor with a 400 ms deadline per part |
| Gradio | [space/](space/): a small web demo you can run locally or on Hugging Face Spaces |
| MCP (Claude Desktop, Cursor and others) | `pip install "simthinkd[mcp]"`, then `python -m simthinkd.integrations.mcp_server` |
| LangChain / LangGraph | `from simthinkd.integrations.langchain_tool import simthinkd_tool` |

## How it works

- **Input**: the situation sentence, the goal and each action's description become hashed features: words, word pairs and three-letter pieces. There is no pretrained language model inside.
- **Model**: a small two-layer network scores every offered action. It sees all actions at once and gives calibrated probabilities.
- **Training**: it starts from random weights and learns from the teacher's choices. The best checkpoint is picked on held-out data.
- **Why it matters**: in a 35 Hz game, a decision that takes longer than 28.6 ms is a missed tick. Our paper separates the cost of decision time from the quality of the decision ([docs/PAPER.md](docs/PAPER.md)).

## Limits

- At most 8 actions per decision.
- Text input only. Turn numbers into short words or bins, like "d5" or "ammo25".
- A decider copies its teacher. It is only as good as the teacher's rules.
- Probabilities are calibrated for the decider's own task only.
- A score model returns one number. It gives no probability or error bar with it.

## More

- [Figures from the paper](docs/FIGURES.md)
- [What you can reproduce](docs/REPRODUCE.md)
- [Decision request format](docs/PROTOCOL.md)
- [The factory video on LinkedIn](https://www.linkedin.com/feed/update/urn:li:activity:7510142949981057024/)

## Citation

If you use SimThink D, please cite it with [CITATION.cff](CITATION.cff). GitHub shows a "Cite this repository" button for it.

- Paper: Shin, Lee, Jeong and Kwon, "Separating Decision Time from Decision Quality in the Real-Time Gap of Distilled Deciders: Evidence from a Game and a Conveyor Simulator", [arXiv:2610.04810](https://arxiv.org/abs/2610.04810)

The two bundled deciders are the exact deciders evaluated in the paper (same SHA-256). [docs/REPRODUCE.md](docs/REPRODUCE.md) lists what you can rerun from this repository and what is not released yet.

## Contributing

Bug reports and small pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

The comparison uses [Laya](https://github.com/NandhaKishorM/laya) by Convai Innovations (Apache 2.0), run unchanged through a small adapter. Doom scenes come from [ViZDoom](https://github.com/Farama-Foundation/ViZDoom). See [NOTICE](NOTICE).

## License

Apache 2.0. See [LICENSE](LICENSE).
