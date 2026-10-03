"""Score models end to end: train a risk score (0-100) from the toy inspection task on a CPU, then check it.

    python -X utf8 tests/test_score.py        (needs: pip install "simthinkd[train]")
The teacher is a fixed formula over the toy part, so the right answer is known for every state. Checks: training finishes,
held-out mean absolute error is small and far better than predicting the training mean, the ranking of parts is
preserved, values stay inside [low, high], the saved model reloads with the same hash, scoring needs no PyTorch path.
"""
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import simthinkd  # noqa: E402
from simthinkd import toy  # noqa: E402

SEVERITY = {'minor': 20, 'moderate': 45, 'severe': 75}


def risk(s):
    base = 0 if s['defect'] == 'none' else SEVERITY[s['severity']]
    base += 10 if s['image'] == 'blurry' else 0
    base += 8 if s['belt'] == 'fast' else 0
    base += 5 if s['defect'] != 'none' and s['queue'] == 'long' else 0
    return float(min(100, base))


def data(n, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        s, text = toy.observe(rng)
        out.append((text, risk(s)))
    return out


def main():
    train, test = data(3000, 7), data(400, 99)
    with tempfile.TemporaryDirectory() as tmp:
        s = simthinkd.fit_score(train, goal='Rate how risky this part is, 0 to 100.', out=str(Path(tmp) / 'risk'),
                                low=0, high=100, quiet=True)
        preds = [s.score(t).value for t, _ in test]
        gold = [v for _, v in test]
        mae = sum(abs(p - g) for p, g in zip(preds, gold)) / len(gold)
        mean = sum(v for _, v in train) / len(train)
        base = sum(abs(mean - g) for g in gold) / len(gold)
        pairs = [(i, j) for i in range(0, len(test), 7) for j in range(3, len(test), 11) if gold[i] != gold[j]]
        concord = sum((preds[i] - preds[j]) * (gold[i] - gold[j]) > 0 for i, j in pairs) / len(pairs)
        again = simthinkd.Scorer(str(Path(tmp) / 'risk'))
        checks = [
            (f'held-out MAE {mae:.2f} below 3 points', mae < 3),
            (f'much better than predicting the mean (MAE {base:.2f})', mae < base / 4),
            (f'ranking preserved ({concord:.0%} of pairs in the right order)', concord > 0.9),
            ('values stay in [0, 100]', all(0 <= p <= 100 for p in preds)),
            ('reloaded model has the same hash', again.sha256 == s.sha256),
            ('same value after reload', abs(again.score(test[0][0]).value - preds[0]) < 1e-6),
            (f'scoring time {s.score(test[1][0]).ms:.2f} ms under 10 ms', s.score(test[1][0]).ms < 10),
        ]
    for name, ok in checks:
        print(('PASS ' if ok else 'FAIL ') + name)
    sys.exit(0 if all(ok for _, ok in checks) else 1)


if __name__ == '__main__':
    main()
