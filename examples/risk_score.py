"""Score instead of choose: train a 0-100 risk score for parts on an inspection belt, on a CPU.

    pip install "simthinkd[train]"
    python examples/risk_score.py

The teacher here is a small formula. In your own system it can be any rule or past record that gives a number:
a risk level, a priority, an expected wait. The trained scorer then gives that number in well under a millisecond.
"""
import random

import simthinkd
from simthinkd import toy

SEVERITY = {'minor': 20, 'moderate': 45, 'severe': 75}


def risk(s):
    """The teacher: a made-up risk formula over the toy part."""
    value = 0 if s['defect'] == 'none' else SEVERITY[s['severity']]
    value += 10 if s['image'] == 'blurry' else 0
    value += 8 if s['belt'] == 'fast' else 0
    value += 5 if s['defect'] != 'none' and s['queue'] == 'long' else 0
    return float(min(100, value))


def examples(n, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        state, sentence = toy.observe(rng)
        out.append((sentence, risk(state)))
    return out


if __name__ == '__main__':
    scorer = simthinkd.fit_score(examples(3000, 7), goal='Rate how risky this part is, 0 to 100.',
                                 out='risk_score', low=0, high=100, quiet=True)
    for sentence in ['part: defect none | severity minor | image clear | belt normal | rework queue short',
                     'part: defect scratch | severity moderate | image blurry | belt normal | rework queue short',
                     'part: defect dent | severity severe | image clear | belt fast | rework queue long']:
        print(f'{scorer.score(sentence)}  <-  {sentence}')
