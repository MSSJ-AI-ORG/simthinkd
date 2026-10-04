"""Goal/state/candidate encoder and portable learned policy; no task parser/oracle.

All text is consumed by deterministic hashed word/character n-gram features.
Neural projections, cross-candidate context and scores are learned from scratch.
Hash compression is lossy; this is not a general pretrained language encoder.
"""
import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np

D = 192
OPS = ['CLICK', 'TYPE_TEXT', 'SELECT', 'WAIT', 'SCROLL_DOWN', 'SCROLL_UP', 'DONE', 'BLOCKED']
ROLES = ['link', 'button', 'textbox', 'searchbox', 'combobox', 'checkbox', 'option', 'radio']


def tokens(text):
    return re.findall(r'\w+|[^\w\s]', unicodedata.normalize('NFKC', str(text)).lower())


@lru_cache(maxsize=60000)
def hashed(text):
    words = tokens(text)
    features = ['w:' + t for t in words]
    features += ['b:' + a + ' ' + b for a, b in zip(words, words[1:])]
    features += ['c:' + t[i:i+3] for t in words for i in range(max(0, len(t)-2))]
    result = np.zeros(D, np.float32)
    for value in features:
        number = int.from_bytes(hashlib.blake2s(value.encode(), digest_size=4).digest(), 'little')
        result[number % D] += 1 if number & 256 else -1
    result /= max(float(np.linalg.norm(result)), 1.)
    return result


def text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def without_indices(value):
    if isinstance(value, dict):
        return {k: without_indices(v) for k, v in value.items() if k != 'index'}
    if isinstance(value, list):
        return sorted([without_indices(v) for v in value], key=text)
    return value


def rows_for(body):
    questions = body.get('questions', {})
    if 'operation' not in questions:
        raise ValueError('This decider answers operation/target questions only')
    rows, operations = [], list(questions['operation']['criteria'])
    for group, op in enumerate(operations):
        head = op.lower() + '_target'
        if head in questions:
            for key, value in questions[head]['criteria'].items():
                rows.append({'operation': op, 'target': key, 'head': head, 'group': group, 'criterion': value})
        else:
            rows.append({'operation': op, 'target': None, 'head': None, 'group': group,
                         'criterion': {'element': op, 'description': questions['operation']['criteria'][op]}})
    if not rows or len(rows) > 1500:
        raise ValueError('Invalid offered action space')
    return rows, operations


def overlap(a, b):
    aa, bb = set(tokens(a)), set(tokens(b))
    return [len(aa & bb)/max(len(aa), 1), len(aa & bb)/max(len(bb), 1),
            float(bool(str(b)) and str(b).casefold() in str(a).casefold())]


def encode(body):
    rows, operations = rows_for(body)
    instructions = body['questions']['operation'].get('instructions', {})
    goal = text(instructions.get('goal', ''))
    state = body['state']
    page = text(state.get('page', {}))
    history = text(state.get('recent_actions', []))
    page_state = state.get('page', {}) if isinstance(state.get('page', {}), dict) else {}
    page_text = text(page_state.get('title', '')) + '\n' + text(page_state.get('text', ''))
    recent = state.get('recent_actions') if isinstance(state.get('recent_actions'), list) else []
    recent = [a for a in recent if isinstance(a, dict)]
    # Order is preserved by the caller; the last entry is the most recent action.
    recent_labels = [str(a.get('action', '')).strip().casefold() for a in recent]
    last_changed = float(bool(recent[-1].get('page_changed'))) if recent else 0.
    # Preserve all observed fields, removing only arbitrary indexing identities.
    elements = without_indices(state.get('elements', []))
    context = text(elements) + '\n' + text(instructions.get('rules', ''))
    shared = [hashed(goal), hashed(page), hashed(history), hashed(context)]
    goal_words = tokens(goal)
    result = []
    for row in rows:
        c = row['criterion']
        c = c if isinstance(c, dict) else {'element': text(c)}
        label = re.sub(r'^\[[^\]]+\]\s*', '', c.get('element', ''))
        value = text(c.get('current_value', ''))
        local = text({**c, 'element': label, 'operation': row['operation']})
        # Generic alignment windows retain order/negation context without parsing goals.
        matching = set(tokens(label + ' ' + value))
        positions = [i for i, word in enumerate(goal_words) if word in matching]
        focus = ' | '.join(' '.join(goal_words[max(0, i-3):i+4]) for i in positions)
        numeric = [float(row['operation'] == op) for op in OPS]
        numeric += [float(c.get('role') == role) for role in ROLES]
        numeric += [float(str(c.get(key, '')).lower() == flag)
                    for key in ['checked', 'selected', 'expanded'] for flag in ['true', 'false']]
        numeric += [float(bool(value)), min(len(rows), 100)/100., min(len(positions), 20)/20.]
        numeric += overlap(goal, label) + overlap(goal, value) + overlap(page, label) + overlap(history, label)
        # Generic pair interactions preserve comparison evidence before compression.
        local_hash = hashed(local)
        products = [hashed(goal)*local_hash, hashed(goal)*hashed(page), hashed(page)*local_hash]
        def char_overlap(a, b):
            def grams(v):
                v = unicodedata.normalize('NFKC', str(v)).lower()
                return {v[i:i+2] for i in range(max(0, len(v)-1)) if not v[i:i+2].isspace()}
            aa, bb = grams(a), grams(b)
            return [len(aa & bb)/max(len(aa), 1), len(aa & bb)/max(len(bb), 1)]
        numeric += char_overlap(goal, label) + char_overlap(goal, page)
        # Recency of this candidate itself: a bag overlap cannot tell order from count.
        key = label.strip().casefold()
        seen = [i for i, name in enumerate(recent_labels) if name and name == key]
        distance = len(recent_labels) - 1 - seen[-1] if seen else None
        numeric += [0. if distance is None else 1./(1.+distance),
                    min(len(seen), 5)/5.,
                    float(distance == 0),
                    float(distance == 0)*last_changed,
                    float(len(seen) >= 2),
                    min(len(recent_labels), 10)/10.]
        # DONE carries no target, so page agreement has to reach its own row explicitly.
        is_done = float(row['operation'] == 'DONE')
        page_match = overlap(goal, page_text) + char_overlap(goal, page_text)
        numeric += page_match + [is_done*v for v in page_match]
        result.append(np.concatenate([*shared, hashed(local), hashed(focus), *products, np.array(numeric, np.float32)]))
    return np.stack(result), np.array([r['group'] for r in rows], np.int64), rows, operations


def softmax(v):
    ex = np.exp(v - np.max(v))
    return ex / ex.sum()


def distributions(scores, groups, temperature=1.):
    scores = scores / temperature
    op_scores, conditional = [], {}
    for g in sorted(set(groups.tolist())):
        where = np.flatnonzero(groups == g)
        s = scores[where]
        op_scores.append(float(np.max(s) + np.log(np.exp(s-np.max(s)).mean())))
        conditional[g] = softmax(s)
    op = softmax(np.asarray(op_scores))
    joint = np.zeros(len(scores))
    for g, p in conditional.items():
        joint[groups == g] = op[g] * p
    return op, conditional, joint


class Policy:
    def __init__(self, path):
        self.path = Path(path)
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with np.load(path, allow_pickle=False) as saved:
            self.w = {key: saved[key].copy() for key in saved.files}
        self.temperature = float(self.w.get('temperature', 1.))

    def scores(self, x):
        w = self.w
        h = np.maximum(0, x @ w['local.weight'].T + w['local.bias'])
        context = np.concatenate([h.mean(0), h.max(0)])
        z = np.concatenate([h, np.broadcast_to(context, (len(h), len(context)))], axis=1)
        z = np.maximum(0, z @ w['context.weight'].T + w['context.bias'])
        return (z @ w['score.weight'].T + w['score.bias'])[:, 0]

    def predict(self, body):
        return self.decode(encode(body), self.scores)

    def decode(self, encoded, scores):
        x, groups, rows, operations = encoded
        op, conditional, joint = distributions(scores if not callable(scores) else scores(x), groups, self.temperature)
        chosen_group = int(op.argmax())
        indices = np.flatnonzero(groups == chosen_group)
        chosen = rows[int(indices[conditional[chosen_group].argmax()])]
        return chosen, op, conditional, joint, rows, operations

    def scores_batch(self, blocks):
        """Scores for many encoded blocks in one padded pass. A block is the row matrix of one question;
        context pooling (mean, max) stays inside its block, so blocks never influence each other."""
        sizes = np.array([len(b) for b in blocks])
        starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
        w = self.w
        # All rows of all blocks go through each layer as one matrix product; only the pooling is per block.
        h = np.maximum(0, np.concatenate(blocks) @ w['local.weight'].T + w['local.bias'])
        context = np.concatenate([np.add.reduceat(h, starts) / sizes[:, None].astype(h.dtype), np.maximum.reduceat(h, starts)], axis=1)
        z = np.concatenate([h, np.repeat(context, sizes, axis=0)], axis=1)
        z = np.maximum(0, z @ w['context.weight'].T + w['context.bias'])
        s = (z @ w['score.weight'].T + w['score.bias'])[:, 0]
        return np.split(s, np.cumsum(sizes)[:-1])

    def predict_batch(self, bodies):
        """predict() for many requests: encoding is per request, the network runs once over all of them."""
        encoded = [encode(b) for b in bodies]
        return [self.decode(e, s) for e, s in zip(encoded, self.scores_batch([e[0] for e in encoded]))]
