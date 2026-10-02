"""Train a decider from your own examples. Needs PyTorch (`pip install "simthinkd[train]"`); inference needs only NumPy.

    import simthinkd
    d = simthinkd.fit(examples, actions, goal="Ship only good parts.", out="my_decider")
    d.decide("part: defect dent | severity severe | image clear")

`examples` is a list of (situation sentence, action name) pairs, usually written by a rule teacher running in your
simulator. The model is a randomly initialised small ranker (no pretrained weights), trained with sampled residual
rewards against a proper scoring rule (Brier); the checkpoint with the lowest validation Brier is kept and its
temperature is fitted on a separate calibration split. Splits are made by a hash of each example's id.

Command line (folder of train/validation/calibration .jsonl.gz rows, see docs/TRAINING.md):
    simthinkd train --data data/toy --out models/toy --steps 600
"""
import copy
import gzip
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .core import Decider, build_request
from .policy import encode

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')


def _torch():
    try:
        import torch
    except ImportError as error:
        raise ImportError('training needs PyTorch: pip install "simthinkd[train]"') from error
    return torch


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def split_for(name):
    digit = int(hashlib.sha256(name.encode()).hexdigest(), 16) % 10
    return 'validation' if digit == 0 else 'calibration' if digit == 1 else 'train'


def _ranker(torch, width):
    class Ranker(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.local = torch.nn.Linear(width, 128)
            self.context = torch.nn.Linear(128 * 3, 96)
            self.score = torch.nn.Linear(96, 1)

        def forward(self, x, mask):
            h = torch.relu(self.local(x))
            mean = (h * mask[..., None]).sum(1) / mask.sum(1, keepdim=True)
            maximum = h.masked_fill(~mask[..., None], -1e9).max(1).values
            c = torch.cat([mean, maximum], -1)[:, None].expand(-1, h.shape[1], -1)
            return self.score(torch.relu(self.context(torch.cat([h, c], -1)))).squeeze(-1)
    return Ranker()


def _probabilities(torch, scores, groups, mask, temperature=1.):
    scores = scores / temperature
    membership = (groups[..., None] == torch.arange(8, device=scores.device)) & mask[..., None]
    count = membership.sum(1)
    expanded = scores[..., None].masked_fill(~membership, -1e9)
    denom = torch.logsumexp(expanded, 1)
    op_logits = (denom - count.clamp_min(1).log()).masked_fill(count == 0, -1e9)
    op = torch.softmax(op_logits, -1)
    conditional = torch.exp(expanded - denom[:, None]) * membership
    return (conditional * op[:, None]).sum(-1), op


def _encode_rows(torch, items, device):
    features, groups, labels = [], [], []
    for row in items:
        x, g, candidates, _ = encode(row['request'])
        gold = row['expected']
        op = gold['operation']
        target = gold.get(op.lower() + '_target')
        matches = [i for i, c in enumerate(candidates) if (c['operation'], c['target']) == (op, target)]
        if not matches:
            raise ValueError(f'example {row.get("id")}: expected action {op!r} is not among the offered actions')
        features.append(x)
        groups.append(g)
        labels.append(matches[0])
    maximum = max(len(x) for x in features)
    width = features[0].shape[1]
    xx = np.zeros((len(items), maximum, width), np.float32)
    gg = np.zeros((len(items), maximum), np.int64)
    mm = np.zeros((len(items), maximum), bool)
    for i, (x, g) in enumerate(zip(features, groups)):
        xx[i, :len(x)] = x
        gg[i, :len(x)] = g
        mm[i, :len(x)] = True
    return tuple(torch.as_tensor(v, device=device) for v in [xx, gg, mm, np.array(labels)]), width


def _brier(torch, p, y):
    q = torch.nn.functional.one_hot(y, p.shape[1]).float()
    return ((p - q) ** 2).sum(-1).mean()


def _assess(torch, model, part):
    x, g, m, y = part
    loss = 0.
    with torch.inference_mode():
        for start in range(0, len(x), 128):
            sl = slice(start, start + 128)
            p, _ = _probabilities(torch, model(x[sl], m[sl]), g[sl], m[sl])
            loss += float(_brier(torch, p, y[sl])) * len(x[sl])
    return loss / len(x)


def _fit_one(torch, initial, train, validation, steps, seed, log):
    model = copy.deepcopy(initial)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0015, weight_decay=.0001)
    rng = torch.Generator(device=train[0].device).manual_seed(seed + 2121)
    rewards = torch.Generator(device=train[0].device).manual_seed(seed + 7171)
    x, g, mask, y = train
    best, weights, events, best_step = float('inf'), copy.deepcopy(model.state_dict()), [], 0
    started = time.perf_counter()
    for step in range(steps + 1):
        if step % 100 == 0 or step == steps:
            val = _assess(torch, model, validation)
            events.append({'step': step, 'validation_brier': val})
            if step > 0 and val < best:
                best, weights, best_step = val, copy.deepcopy(model.state_dict()), step
            log({'seed': seed, 'step': step, 'validation_brier': round(val, 6)})
        if step == steps:
            break
        batch = torch.randint(len(x), (96,), generator=rng, device=x.device)
        p, _ = _probabilities(torch, model(x[batch], mask[batch]), g[batch], mask[batch])
        q = torch.nn.functional.one_hot(y[batch], p.shape[1]).float()
        reward = 2 * (q - p).detach()
        baseline = (p.detach() * reward).sum(-1, keepdim=True)
        sampled = torch.multinomial(p.detach(), 32, replacement=True, generator=rewards)
        loss = -((reward - baseline).gather(1, sampled) * p.clamp_min(1e-30).log().gather(1, sampled)).mean()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
    model.load_state_dict(weights)
    model.eval()
    return model, {'seed': seed, 'steps_run': steps, 'selected_step': best_step,
                   'seconds': time.perf_counter() - started, 'validation_brier': best, 'events': events}


def fit_rows(rows, out, steps=600, seed=31, card=None, quiet=False):
    """Train from protocol rows {"id", "request", "expected": {"operation", "<op>_target"?}}; returns a Decider."""
    torch = _torch()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = (lambda record: None) if quiet else (lambda record: print(json.dumps(record), flush=True))
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    torch.use_deterministic_algorithms(True)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    splits = {'train': [], 'validation': [], 'calibration': []}
    for row in rows:
        splits[row.get('split') or split_for(row['id'])].append(row)
    if min(len(v) for v in splits.values()) == 0:
        raise ValueError('need enough examples for train/validation/calibration splits (about 100 or more)')
    parts = {}
    for name, items in splits.items():
        parts[name], width = _encode_rows(torch, items, device)
    torch.manual_seed(seed)
    initial = _ranker(torch, width).to(device)
    model, record = _fit_one(torch, initial, parts['train'], parts['validation'], steps, seed, log)
    cx, cg, cm, cy = parts['calibration']
    with torch.inference_mode():
        scores = torch.cat([model(cx[i:i + 128], cm[i:i + 128]) for i in range(0, len(cx), 128)])
        temperatures = np.geomspace(.5, 3., 25)
        losses = [float(_brier(torch, _probabilities(torch, scores, cg, cm, float(t))[0], cy)) for t in temperatures]
    temperature = float(temperatures[int(np.argmin(losses))])
    arrays = {k: v.detach().cpu().numpy() for k, v in model.state_dict().items()}
    path = out / 'weights.npz'
    np.savez_compressed(path, **arrays, temperature=np.array(temperature))
    card = dict(card or {})
    card.update({'weights': path.name, 'sha256': sha(path), 'temperature': temperature,
                 'parameters': sum(p.numel() for p in model.parameters()),
                 'examples': {k: len(v) for k, v in splits.items()}, 'training': record,
                 'calibration_brier': min(losses), 'device': device, 'torch': torch.__version__,
                 'created_at': datetime.now(timezone.utc).isoformat(),
                 'initialization': 'random (no pretrained weights)'})
    (out / 'decider.json').write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding='utf8')
    return Decider(str(out))


def fit(examples, actions, goal='', out='my_decider', steps=600, seed=31, name=None, quiet=False):
    """Train a decider from (situation sentence, action name) pairs. Returns a ready Decider."""
    if not actions or len(actions) > 8:
        raise ValueError('offer between 1 and 8 actions: {name: short description}')
    rows = []
    for i, item in enumerate(examples):
        state, action = (item['state'], item['action']) if isinstance(item, dict) else item
        if action not in actions:
            raise ValueError(f'example {i}: action {action!r} is not in actions')
        row_id = f'ex{i:07d}:' + hashlib.sha256(state.encode()).hexdigest()[:8]
        rows.append({'id': row_id, 'request': build_request(state, actions, goal), 'expected': {'operation': action}})
    card = {'name': name or Path(out).name, 'actions': dict(actions), 'goal': goal,
            'url': 'sim://custom', 'title': '', 'model': 'simthinkd'}
    return fit_rows(rows, out, steps=steps, seed=seed, card=card, quiet=quiet)


def fit_dir(data, out, steps=600, seed=31, quiet=False):
    """Train from a folder holding train/validation/calibration .jsonl.gz protocol rows."""
    rows = []
    for split in ['train', 'validation', 'calibration']:
        with gzip.open(Path(data) / f'{split}.jsonl.gz', 'rt', encoding='utf8') as stream:
            rows += [dict(json.loads(line), split=split) for line in stream]
    first = rows[0]['request']
    card = {'name': Path(out).name, 'goal': first['questions']['operation'].get('instructions', {}).get('goal', ''),
            'actions': {k: (v.get('description') if isinstance(v, dict) else v)
                        for k, v in first['questions']['operation']['criteria'].items()},
            'url': first['state']['page'].get('url', 'sim://custom'), 'title': first['state']['page'].get('title', ''),
            'model': first.get('model', 'simthinkd'),
            'data_sha256': {s: sha(Path(data) / f'{s}.jsonl.gz') for s in ['train', 'validation', 'calibration']}}
    return fit_rows(rows, out, steps=steps, seed=seed, card=card, quiet=quiet)
