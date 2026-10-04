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
- Requests whose target questions have different numbers of candidates batch correctly; an empty batch returns `[]`; a block with no rows is refused.

## Measure it: `simthinkd bench --batch`

Decisions per second on the bundled Doom states: one at a time (`predict`) and in batches of 1, 10, 100 and 1000
(`predict_batch`), both end to end. A separate pass shows where batch time goes. One run on a desktop CPU (numpy, 7 actions
per decision, 1000 decisions, best of 3):

| | end to end, per second | network alone, per second | encoding text | network | building answers |
|---|---|---|---|---|---|
| one at a time | 1,004 | | | | |
| batch 1 | 722 | 6,366 | 75% | 11% | 14% |
| batch 100 | 787 | 31,320 | 83% | 2% | 14% |
| batch 1000 | 709 | 33,488 | 85% | 2% | 13% |

Read this plainly: batching makes the network itself about 5 times faster, but end to end a batch is not faster than one
request at a time here, because about 85% of the time goes to turning text into features, which is still done one request
at a time in Python. Batching pays off once encoding is fast (for example run in several processes, cached, or done before
the batch), or when the network runs on a GPU while the CPU encodes the next batch. Your numbers will differ with your
machine.
