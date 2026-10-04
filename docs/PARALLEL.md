# Parallel questions and batches

SimThink D can work on many decisions at once in two ways. Both use the same weights as `predict()`, so the answers do not change.

## 1. Several questions about one situation: `Decider.ask(body)`

Put more than one question in `questions`. Each question has a type:

| type | criteria | answer |
|---|---|---|
| `choice` | `{name: description}` | `choice`, `probabilities`, `confidence` |
| `score` | a list of 2 to 10 levels, lowest first | `score` (1 = first level), `probabilities`, `confidence` |
| `noul` | optional `{"true": ..., "false": ...}` | `noul` = probability of true |

```python
from simthinkd import Decider
d = Decider("doom-defend")
body = d.request("seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25")
body["questions"]["urgency"] = {"type": "score", "instructions": {"goal": "How urgent is it?"},
                                "criteria": ["calm", "some pressure", "under attack", "about to die"]}
body["questions"]["save_ammo"] = {"type": "noul", "instructions": {"goal": "Should we save ammunition?"}}
print(d.ask(body)["answers"])
```

The usual `operation` question (with its `<operation>_target` questions) gives the same answer as `predict()`.
Every other question is answered on its own: it never sees the other questions, so adding or removing a question does not
change any other answer. A request may also carry only general questions and no `operation`.

A decider answers well only the kinds of questions it was trained on. To train a general question, write each one as its
own `operation` request on the same state (one row per question) and train as usual; `ask()` then answers them together.

## 2. Many situations at once: `predict_batch(bodies)` and `ask_batch(bodies)`

```python
answers = d.predict_batch([body_1, body_2, body_3])   # same as [d.predict(b) for b in ...]
```

Each request is turned into features on its own; then all candidate rows of all requests go through each layer of the
network as one matrix product. Only the pooling across candidates is done per question.

## Guarantees (tested in `tests/test_parallel.py`)

- `predict_batch` gives the same choices as `predict` one at a time, and probabilities within 1e-6 (the network uses 32-bit
  floats; a different matrix shape can round the last bits differently).
- `ask` on a plain request gives the same answer as `predict`.
- Adding other questions, including one with 40 options, does not change a question's answer.
- Bad questions (a score with one level, a noul without true/false, an unknown type, a choice without options) are refused.

## Measure it: `simthinkd bench --batch`

Decisions per second on the bundled Doom states, one at a time and in batches of 1, 10, 100 and 1000, and the share of time
spent turning text into features. One run on a desktop CPU (numpy, 7 actions per decision):

| | decisions per second | network alone | time spent encoding text |
|---|---|---|---|
| one at a time (`predict`) | 865 | | |
| batch 1 | 977 | 3,694 | 74% |
| batch 100 | 1,078 | 6,404 | 83% |
| batch 1000 | 1,097 | 6,489 | 83% |

Batching makes the network itself about 1.7 times faster, but most of the time goes to turning text into features, which is
still done one request at a time. Speeding up that step, for example by running it in several processes, is the next step
for higher throughput. Your numbers will differ with your CPU.
