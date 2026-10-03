"""Score models: the same small network as a decider, but it returns one number instead of picking an action.

    import simthinkd
    s = simthinkd.fit_score(examples, goal="Rate the risk of this part.", out="risk", low=0, high=100)
    s.score("part: defect dent | severity severe | image clear | belt normal | rework queue long")
    # Score(value=87.3, ms=1.1)

`examples` is a list of (situation sentence, number) pairs. Training needs PyTorch; scoring needs only NumPy.
Targets are standardised, the network is trained with a squared-error loss, and the checkpoint with the lowest
validation mean absolute error is kept. Splits are made by a hash of each example, as in `fit`.
"""
import copy
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .core import build_request
from .policy import Policy, encode
from .train import _encode_rows, _ranker, _torch, sha, split_for

ACTION = {'SCORE': 'Return one number for this situation.'}


@dataclass
class Score:
    value: float
    ms: float = 0.0

    def __str__(self):
        return f'{self.value:.2f} ({self.ms:.2f} ms)'


class Scorer:
    """A trained score model. `Scorer("path/to/folder")`."""

    def __init__(self, path):
        path = Path(path)
        self.card = json.loads((path / 'decider.json').read_text(encoding='utf8'))
        if self.card.get('kind') != 'score':
            raise ValueError(f'{path} is not a score model (use Decider for action models)')
        self.policy = Policy(path / self.card['weights'])
        self.sha256 = self.policy.digest

    def score(self, state):
        body = build_request(state, ACTION, self.card.get('goal', ''))
        start = time.perf_counter()
        x, _, _, _ = encode(body)
        raw = float(self.policy.scores(x)[0])
        value = raw * self.card['std'] + self.card['mean']
        low, high = self.card.get('low'), self.card.get('high')
        if low is not None:
            value = max(low, value)
        if high is not None:
            value = min(high, value)
        return Score(value, (time.perf_counter() - start) * 1000)

    def __repr__(self):
        return f'Scorer({self.card.get("name")!r}, sha256={self.sha256[:12]})'


def _mae(torch, model, part, mean, std):
    x, _, m, y = part
    with torch.inference_mode():
        pred = torch.cat([model(x[i:i + 256], m[i:i + 256])[:, 0] for i in range(0, len(x), 256)])
    return float((pred * std + mean - y).abs().mean())


def fit_score(examples, goal='', out='my_scorer', steps=1500, seed=31, low=None, high=None, name=None, quiet=False):
    """Train a score model from (situation sentence, number) pairs. Returns a ready Scorer."""
    torch = _torch()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = (lambda record: None) if quiet else (lambda record: print(json.dumps(record), flush=True))
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    torch.use_deterministic_algorithms(True)
    device = 'cpu'
    splits = {'train': [], 'validation': [], 'calibration': []}
    for i, item in enumerate(examples):
        state, value = (item['state'], item['value']) if isinstance(item, dict) else item
        row_id = f'sc{i:07d}:' + hashlib.sha256(state.encode()).hexdigest()[:8]
        splits[split_for(row_id)].append({'id': row_id, 'request': build_request(state, ACTION, goal),
                                          'expected': {'operation': 'SCORE'}, 'value': float(value)})
    splits['validation'] += splits.pop('calibration')
    if min(len(v) for v in splits.values()) == 0:
        raise ValueError('need enough examples for train/validation splits (about 100 or more)')
    values = np.array([r['value'] for r in splits['train']], np.float32)
    mean, std = float(values.mean()), float(values.std() or 1.)
    parts = {}
    for name_, items in splits.items():
        (x, g, m, _), width = _encode_rows(torch, items, device)
        parts[name_] = (x, g, m, torch.tensor([r['value'] for r in items], dtype=torch.float32))
    torch.manual_seed(seed)
    model = _ranker(torch, width).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.0001)
    rng = torch.Generator().manual_seed(seed + 2121)
    x, _, m, y = parts['train']
    target = (y - mean) / std
    best, weights, best_step, events = float('inf'), copy.deepcopy(model.state_dict()), 0, []
    started = time.perf_counter()
    for step in range(steps + 1):
        if step % 100 == 0 or step == steps:
            model.eval()
            val = _mae(torch, model, parts['validation'], mean, std)
            model.train()
            events.append({'step': step, 'validation_mae': val})
            if val < best:
                best, weights, best_step = val, copy.deepcopy(model.state_dict()), step
            log({'seed': seed, 'step': step, 'validation_mae': round(val, 6)})
        if step == steps:
            break
        batch = torch.randint(len(x), (min(96, len(x)),), generator=rng)
        pred = model(x[batch], m[batch])[:, 0]
        loss = ((pred - target[batch]) ** 2).mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    model.load_state_dict(weights)
    model.eval()
    arrays = {k: v.detach().cpu().numpy() for k, v in model.state_dict().items()}
    path = out / 'weights.npz'
    np.savez_compressed(path, **arrays, temperature=np.array(1.0))
    card = {'kind': 'score', 'name': name or out.name, 'goal': goal, 'weights': path.name, 'sha256': sha(path),
            'mean': mean, 'std': std, 'low': low, 'high': high,
            'parameters': sum(p.numel() for p in model.parameters()),
            'examples': {k: len(v) for k, v in splits.items()},
            'training': {'seed': seed, 'steps_run': steps, 'selected_step': best_step, 'validation_mae': best,
                         'seconds': time.perf_counter() - started, 'events': events},
            'torch': torch.__version__, 'created_at': datetime.now(timezone.utc).isoformat(),
            'initialization': 'random (no pretrained weights)'}
    (out / 'decider.json').write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding='utf8')
    return Scorer(out)
