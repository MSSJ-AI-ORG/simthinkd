"""Feature adapters: turn one kind of observation into the short sentence a decider reads. Same decider, different input.

    ScreenAdapter()      screenshot pixels (+ window title, previous action) -> 'title: Sign in | prev: START | screen: g00w ...'
    PipelineAdapter()    pipeline step (request meta, gate verdict)          -> 'step: draft | request: kind proposal ; pages 12 | gate: lint FAIL | reasons: ...'
    VectorAdapter([...]) part of a robot observation vector                  -> 'obs: base_vx q5 | yaw_rate q3'

Each adapter is a plain callable, so `Router(decider, skills, adapter=ScreenAdapter())` routes screenshots directly.
Adapters are deterministic and need only NumPy; train the decider on sentences made by the same adapter.
"""
import json
import math

import numpy as np

SATURATED = 'yorgbn'


def color_class(r, g, b):
    """One colour letter for an RGB value: w l m d (white to dark grey), y o r g b n (yellow orange red green blue other)."""
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 28:
        return 'w' if mx > 235 else 'l' if mx > 200 else 'm' if mx > 110 else 'd'
    if r > 150 and g > 150 and b < 120:
        return 'y'
    if r >= g and r >= b:
        return 'o' if g > 90 else 'r'
    if g >= r and g >= b:
        return 'g'
    return 'b' if b - r > 40 else 'n'


def _box(pixels, height, width):
    """Area-average resize to (height, width), rounded to whole values. Exact block means when the sizes divide evenly."""
    h, w = pixels.shape[:2]
    if h < height or w < width:
        raise ValueError(f'the screenshot ({w}x{h}) is smaller than the grid needs ({width}x{height})')
    if h % height == 0 and w % width == 0:
        out = pixels.reshape(height, h // height, width, w // width, 3).mean(axis=(1, 3))
    else:
        rows = np.linspace(0, h, height + 1).round().astype(int)
        cols = np.linspace(0, w, width + 1).round().astype(int)
        out = np.array([[pixels[rows[i]:rows[i + 1], cols[j]:cols[j + 1]].reshape(-1, 3).mean(0)
                         for j in range(width)] for i in range(height)])
    return np.floor(out + 0.5).astype(np.int64)


def screen_tokens(pixels, cols=8, rows=6):
    """Colour-grid tokens of a screenshot (the feature of experiment v2.1).

    The image is box-resized to (8*cols) x (8*rows); each 8x8 cell gives a token g<row><col><mean colour class>, plus
    a<row><col><colour> when at least 4 of its 64 pixels have a saturated colour (the most frequent one; a tie goes to the
    colour seen first in the cell). pixels: an H x W x 3 array of 0-255 values (RGB), at least that many pixels."""
    if not (1 <= cols <= 10 and 1 <= rows <= 10):
        raise ValueError('cols and rows must be between 1 and 10')
    px = np.asarray(pixels)
    if px.ndim != 3 or px.shape[2] < 3:
        raise ValueError('pixels must be an H x W x 3 RGB array')
    small = _box(px[:, :, :3].astype(np.float64), rows * 8, cols * 8)
    tokens = []
    for cy in range(rows):
        for cx in range(cols):
            cell = small[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8].reshape(-1, 3)
            mean = cell.sum(0) // 64
            tokens.append(f'g{cy}{cx}{color_class(*(int(v) for v in mean))}')
            sat = [c for c in (color_class(*(int(v) for v in p)) for p in cell) if c in SATURATED]
            if len(sat) >= 4:
                top = max(dict.fromkeys(sat), key=sat.count)  # dict keeps first-seen order: deterministic ties
                tokens.append(f'a{cy}{cx}{top}')
    return ' '.join(tokens)


class ScreenAdapter:
    """Screen observation -> sentence. An observation is a dict {'pixels', 'title', 'prev'} or the pixel array alone.

    with_title / with_prev False gives the pixel-only sentence 'screen: ...' (the router_visual model of v2.1)."""

    def __init__(self, cols=8, rows=6, with_title=True, with_prev=True):
        if not (1 <= cols <= 10 and 1 <= rows <= 10):
            raise ValueError('cols and rows must be between 1 and 10')
        self.cols, self.rows, self.with_title, self.with_prev = cols, rows, with_title, with_prev

    def __call__(self, observation):
        if isinstance(observation, dict):
            if 'pixels' not in observation:
                raise ValueError("a screen observation needs 'pixels'")
            pixels, title, prev = observation['pixels'], observation.get('title', ''), observation.get('prev')
        else:
            pixels, title, prev = observation, '', None
        parts = []
        if self.with_title:
            parts.append(f'title: {title or ""}')
        if self.with_prev:
            parts.append(f'prev: {prev or "START"}')
        parts.append('screen: ' + screen_tokens(pixels, self.cols, self.rows))
        return ' | '.join(parts)


def _value(v):
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, (dict, list, tuple)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return ' '.join(str(v).split()) or '-'


class PipelineAdapter:
    """Pipeline step -> sentence, for routing inside a fixed pipeline (which step next, which gate failure, which model).

    An observation is a dict {'step': name, 'request': {meta}, 'gate': {'name', 'verdict', 'reasons'}}; every part is
    optional but the observation must be a dict. fields: the request keys to keep, in this order (None: all, sorted)."""

    def __init__(self, fields=None, max_reasons=5):
        if fields is not None and (isinstance(fields, str) or not all(isinstance(f, str) and f for f in fields)):
            raise ValueError('fields must be a list of request keys')
        if not isinstance(max_reasons, int) or max_reasons < 0:
            raise ValueError('max_reasons must be a whole number >= 0')
        self.fields, self.max_reasons = (list(fields) if fields is not None else None), max_reasons

    def __call__(self, observation):
        if not isinstance(observation, dict):
            raise ValueError('a pipeline observation is a dict with step, request and gate')
        request = observation.get('request') or {}
        if not isinstance(request, dict):
            raise ValueError('request must be a dict of meta fields')
        keys = self.fields if self.fields is not None else sorted(request)
        meta = ' ; '.join(f'{k} {_value(request[k])}' for k in keys if k in request) or 'none'
        parts = [f'step: {_value(observation.get("step") or "-")}', f'request: {meta}']
        gate = observation.get('gate')
        if gate is None:
            parts.append('gate: none')
        else:
            if not isinstance(gate, dict):
                raise ValueError('gate must be a dict with name, verdict and reasons')
            parts.append(f'gate: {_value(gate.get("name") or "-")} {_value(gate.get("verdict") or "-").upper()}')
            reasons = [_value(r) for r in (gate.get('reasons') or [])][:self.max_reasons]
            if reasons:
                parts.append('reasons: ' + ' ; '.join(reasons))
        return ' | '.join(parts)


class VectorAdapter:
    """Part of a numeric observation vector (e.g. a robot's 61 observations) -> sentence of quantised levels.

    indices: which entries to use; names: one word per entry (default x<index>); low/high: the range per entry (a number
    or one per entry), clipped; levels: how many bins (2-64). Entry 0.42 in [-1, 1] with 8 levels becomes 'q5'."""

    def __init__(self, indices, names=None, low=-1.0, high=1.0, levels=8, prefix='obs'):
        self.indices = [int(i) for i in indices]
        if not self.indices:
            raise ValueError('choose at least one index')
        if any(i < 0 for i in self.indices) or len(set(self.indices)) != len(self.indices):
            raise ValueError('indices must be distinct and >= 0')
        self.names = list(names) if names is not None else [f'x{i}' for i in self.indices]
        if len(self.names) != len(self.indices) or not all(isinstance(n, str) and n and ' ' not in n for n in self.names):
            raise ValueError('give one name (one word) per index')
        n = len(self.indices)
        self.low = np.broadcast_to(np.asarray(low, np.float64), (n,)).copy()
        self.high = np.broadcast_to(np.asarray(high, np.float64), (n,)).copy()
        if not np.all(np.isfinite(self.low)) or not np.all(np.isfinite(self.high)) or np.any(self.high <= self.low):
            raise ValueError('every range needs finite low < high')
        if not isinstance(levels, int) or not 2 <= levels <= 64:
            raise ValueError('levels must be a whole number from 2 to 64')
        self.levels, self.prefix = levels, prefix

    def level(self, k, value):
        """Bin of one value for entry k (0 .. levels-1)."""
        span = (min(max(value, self.low[k]), self.high[k]) - self.low[k]) / (self.high[k] - self.low[k])
        return min(int(math.floor(span * self.levels)), self.levels - 1)

    def __call__(self, observation):
        vector = np.asarray(observation, np.float64).reshape(-1)
        if max(self.indices) >= len(vector):
            raise ValueError(f'the observation has {len(vector)} entries; index {max(self.indices)} is out of range')
        values = vector[self.indices]
        if not np.all(np.isfinite(values)):
            raise ValueError('the observation has a missing or infinite value in the chosen entries')
        body = ' | '.join(f'{name} q{self.level(k, v)}' for k, (name, v) in enumerate(zip(self.names, values)))
        return f'{self.prefix}: {body}'
