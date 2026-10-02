"""A toy domain for trying `simthinkd.fit` in seconds: a part passes an inspection station on a conveyor.

    import simthinkd
    from simthinkd import toy
    d = simthinkd.fit(toy.examples(3000), toy.ACTIONS, goal=toy.GOAL, out="inspection")
    d.decide("part: defect dent | severity severe | image clear | belt normal | rework queue long")

Replace `observe()` and `teacher()` with your simulator's perception (exact state -> short binned sentence)
and rule teacher (exact state -> action). That pair is all a new domain needs.
"""
import random

GOAL = 'Ship only good parts without stopping the line.'
ACTIONS = {
    'PASS': 'Let the part continue to packing.',
    'REJECT': 'Divert the part to the reject bin.',
    'REWORK': 'Send the part to the rework loop.',
    'SLOW_BELT': 'Slow the conveyor for a closer look.',
    'ESCALATE': 'Hold the part and call a human inspector.',
}


def observe(rng):
    """A random part: exact state (for the teacher) and its binned sentence (for the decider)."""
    s = {'defect': rng.choice(['none'] * 5 + ['scratch', 'dent', 'missing', 'stain']),
         'severity': rng.choice(['minor', 'moderate', 'severe']),
         'image': rng.choice(['clear', 'blurry']),
         'belt': rng.choice(['normal', 'fast']),
         'queue': rng.choice(['short', 'long'])}
    text = (f"part: defect {s['defect']} | severity {s['severity']} | image {s['image']} | "
            f"belt {s['belt']} | rework queue {s['queue']}")
    return s, text


def teacher(s):
    """The rule teacher the decider learns to imitate."""
    if s['defect'] == 'none':
        return 'SLOW_BELT' if s['image'] == 'blurry' and s['belt'] == 'fast' else 'PASS'
    if s['image'] == 'blurry':
        return 'ESCALATE'
    if s['defect'] == 'stain' or (s['severity'] == 'minor' and s['queue'] == 'short'):
        return 'REWORK'
    return 'REJECT'


def examples(n=3000, seed=0):
    """n (situation sentence, teacher action) pairs."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        s, text = observe(rng)
        out.append((text, teacher(s)))
    return out
