"""DOM input for the router: read the page structure as well as (or instead of) the screenshot.

    DomAdapter()                       DOM snapshot (+ title, previous action) -> 'title: Export | path: /index.html | prev: START | dom: button submit_request ; ...'
    CombinedAdapter()                  screenshot + DOM snapshot               -> the ScreenAdapter sentence + ' | dom: ...'
    DomVerifier.fit(...)               capture decides, DOM checks             -> agree / disagree (with a reason)
    VerifiedRouter(router, verifier)   a Router whose fast actions must pass the DOM check, else a hand-over 'verify_disagree'

A DOM snapshot is a small dict that you collect from the page (for a browser, `DOM_SNAPSHOT_JS` through the Chrome DevTools
protocol `Runtime.evaluate`, returnByValue):

    {'title': 'Export - Demo Portal', 'path': '/index.html',
     'elements': [{'role': 'button', 'name': 'Submit request', 'enabled': True, 'covered': False, 'x': 362, 'y': 615, 'w': 300, 'h': 50}, ...]}

Only visible interactive elements are listed: role (or tag), accessible name or visible text, enabled, covered (another
element sits on its centre). What a person typed into a field is never read: the snapshot script does not touch `.value`,
and the adapter ignores every key it does not know (so a stray 'value' never reaches the sentence). The URL is reduced to
its path (no query, no fragment). The sentence is bounded (max_elements, max_name) and its order is deterministic
(position, then role, then name).

This module does not change router.py, relearn.py or adapters.py (they are frozen by the sealed router_screen example).
"""
import re
import time
import unicodedata
from dataclasses import dataclass

from .adapters import ScreenAdapter
from .router import Route

VERIFY_DISAGREE = 'verify_disagree'
DOM_SCHEMA = 'simthinkd-dom/1'

# Runs inside the page. Returns a snapshot dict; never reads .value of any element.
DOM_SNAPSHOT_JS = r"""(() => {
  const t0 = performance.now();
  const sel = 'button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=link],[role=checkbox],[role=tab],' +
              '[role=menuitem],[role=option],[role=radio],[role=switch],[tabindex]:not([tabindex="-1"])';
  const W = window.innerWidth, H = window.innerHeight, out = [];
  const roleOf = (e) => {
    const r = e.getAttribute('role'); if (r) return r;
    const tag = e.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') { const ty = (e.getAttribute('type') || 'text').toLowerCase();
      if (ty === 'checkbox' || ty === 'radio') return ty;
      if (ty === 'submit' || ty === 'button' || ty === 'reset') return 'button';
      return 'textbox'; }
    return tag === 'button' ? 'button' : tag; };
  const nameOf = (e) => {
    let n = e.getAttribute('aria-label') || '';
    if (!n && e.labels && e.labels.length) n = e.labels[0].innerText || '';
    const tag = e.tagName.toLowerCase();
    if (!n && tag === 'input') { const ty = (e.getAttribute('type') || 'text').toLowerCase();
      n = (ty === 'submit' || ty === 'button') ? (e.getAttribute('value') || '') : (e.getAttribute('placeholder') || ''); }
    if (!n && tag !== 'input' && tag !== 'textarea' && tag !== 'select') n = e.innerText || '';
    if (!n) n = e.getAttribute('title') || e.getAttribute('alt') || '';
    return n.replace(/\s+/g, ' ').trim().slice(0, 60); };
  for (const e of document.querySelectorAll(sel)) {
    const r = e.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || r.right <= 0 || r.bottom <= 0 || r.left >= W || r.top >= H) continue;
    const s = getComputedStyle(e);
    if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0) continue;
    const cx = Math.min(W - 1, Math.max(0, r.left + r.width / 2)), cy = Math.min(H - 1, Math.max(0, r.top + r.height / 2));
    const hit = document.elementFromPoint(cx, cy);
    out.push({role: roleOf(e), name: nameOf(e), enabled: !(e.disabled || e.getAttribute('aria-disabled') === 'true'),
              covered: !(hit && (hit === e || e.contains(hit))), x: Math.round(r.left), y: Math.round(r.top),
              w: Math.round(r.width), h: Math.round(r.height)});
  }
  return {schema: 'simthinkd-dom/1', title: document.title, path: location.pathname, elements: out, ms: performance.now() - t0};
})()"""

_KNOWN = ('role', 'name', 'enabled', 'covered', 'x', 'y', 'w', 'h')


def _word(text, limit):
    """One lower-case word for a role or name: NFKC, letters/digits kept, everything else -> '_', cut to `limit` chars."""
    t = unicodedata.normalize('NFKC', str(text or '')).lower()
    t = re.sub(r'[^\w]+', '_', t, flags=re.UNICODE).strip('_')
    return t[:limit].rstrip('_')


def _path(snapshot):
    p = snapshot.get('path')
    if p is None:
        url = str(snapshot.get('url') or '')
        p = re.sub(r'^[a-z][a-z0-9+.-]*://[^/]*', '', url, flags=re.I)
    p = re.split(r'[?#]', str(p or ''), maxsplit=1)[0]
    return p or '/'


def _elements(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError('a DOM snapshot is a dict with title, path and elements')
    items = snapshot.get('elements')
    if items is None:
        items = []
    if not isinstance(items, (list, tuple)):
        raise ValueError('elements must be a list of dicts')
    out = []
    for i, e in enumerate(items):
        if not isinstance(e, dict) or not e.get('role'):
            raise ValueError(f'element {i} needs at least a role')
        out.append({k: e[k] for k in _KNOWN if k in e})  # unknown keys (e.g. a value) are dropped here
    return out


def element_key(element, max_name=32):
    """(role, name) of one element, both as words. The key the verifier compares."""
    return _word(element.get('role'), 16) or 'element', _word(element.get('name'), max_name)


def _order(e):
    return (int(float(e.get('y', 0)) // 8), int(float(e.get('x', 0)) // 8), str(e.get('role')), str(e.get('name', '')))


class DomAdapter:
    """DOM observation -> sentence. An observation is a snapshot dict, or a dict {'dom': snapshot, 'title', 'prev'}
    (the outer title wins over the snapshot's own title).

    max_elements: keep at most this many elements (in reading order: top to bottom, left to right); max_name: characters
    per name. with_title / with_path / with_prev: include those parts. Elements that are disabled or covered carry the
    word 'disabled' / 'covered'."""

    def __init__(self, max_elements=32, max_name=32, with_title=True, with_path=True, with_prev=True):
        if not isinstance(max_elements, int) or not 1 <= max_elements <= 256:
            raise ValueError('max_elements must be a whole number from 1 to 256')
        if not isinstance(max_name, int) or not 1 <= max_name <= 120:
            raise ValueError('max_name must be a whole number from 1 to 120')
        self.max_elements, self.max_name = max_elements, max_name
        self.with_title, self.with_path, self.with_prev = with_title, with_path, with_prev

    @staticmethod
    def split(observation):
        """(snapshot, title, prev) from either observation form."""
        if not isinstance(observation, dict):
            raise ValueError('a DOM observation is a snapshot dict or {"dom": snapshot, ...}')
        if 'dom' in observation:
            snap = observation['dom']
            title = observation.get('title', snap.get('title', '') if isinstance(snap, dict) else '')
            return snap, title, observation.get('prev')
        return observation, observation.get('title', ''), observation.get('prev')

    def body(self, snapshot):
        """The 'dom: ...' part alone."""
        els = sorted(_elements(snapshot), key=_order)[:self.max_elements]
        words = []
        for e in els:
            role, name = element_key(e, self.max_name)
            w = role + (' ' + name if name else '')
            if e.get('enabled') is False:
                w += ' disabled'
            if e.get('covered'):
                w += ' covered'
            words.append(w)
        return 'dom: ' + (' ; '.join(words) if words else 'none')

    def __call__(self, observation):
        snap, title, prev = self.split(observation)
        parts = []
        if self.with_title:
            parts.append('title: ' + ' '.join(str(title or '').split())[:120])
        if self.with_path:
            parts.append('path: ' + _path(snap)[:80])
        if self.with_prev:
            parts.append(f'prev: {prev or "START"}')
        parts.append(self.body(snap))
        return ' | '.join(parts)


class CombinedAdapter:
    """Screenshot + DOM -> one sentence: the ScreenAdapter sentence (title, previous action, colour grid) followed by the
    DOM part. An observation is a dict {'pixels', 'dom', 'title', 'prev'}. Title and previous action appear once."""

    def __init__(self, screen=None, dom=None):
        self.screen = screen or ScreenAdapter()
        self.dom = dom or DomAdapter()

    def __call__(self, observation):
        if not isinstance(observation, dict) or 'dom' not in observation or 'pixels' not in observation:
            raise ValueError("a combined observation needs 'pixels' and 'dom'")
        return self.screen(observation) + ' | ' + self.dom.body(observation['dom'])


@dataclass(frozen=True)
class Verdict:
    agree: bool
    reason: str = None      # None, 'no_signature', 'missing_elements', 'no_target', 'target_disabled', 'target_covered'
    missing: tuple = ()
    ms: float = 0.0


class DomVerifier:
    """Checks a decision made from the screenshot against the DOM, before the fast action runs.

    signatures: state -> set of (role, name) keys that every training snapshot of that state showed (learned by `fit`).
    targets: action -> (role, name) of the control the scripted action presses (given by whoever wrote the script, like the
    click coordinates). An action with no target (e.g. DONE, or typing into fields) is checked by the signature only.

    verify(state, action, snapshot) agrees only if the state has a signature, all its keys are present, and the action's
    target (if any) is present, enabled and not covered. Any other case is a disagreement with one reason."""

    def __init__(self, signatures, targets=None, max_name=32):
        self.signatures = {s: frozenset(tuple(k) for k in keys) for s, keys in dict(signatures).items()}
        self.targets = {}
        for a, t in dict(targets or {}).items():
            role, name = t
            self.targets[a] = (_word(role, 16), _word(name, max_name))
        self.max_name = max_name

    @classmethod
    def fit(cls, examples, targets=None, min_share=1.0, max_name=32):
        """Learn signatures from (state, snapshot) pairs: a key belongs to the state's signature if it appears in at least
        `min_share` of that state's snapshots (1.0: in all of them)."""
        if not 0 < min_share <= 1:
            raise ValueError('min_share must be in (0, 1]')
        seen, count = {}, {}
        for state, snap in examples:
            keys = {element_key(e, max_name) for e in _elements(snap)}
            count[state] = count.get(state, 0) + 1
            for k in keys:
                seen.setdefault(state, {}).setdefault(k, 0)
                seen[state][k] += 1
            seen.setdefault(state, {})
        sig = {s: {k for k, n in keys.items() if n >= min_share * count[s] - 1e-9} for s, keys in seen.items()}
        return cls(sig, targets, max_name)

    def verify(self, state, action, snapshot):
        t0 = time.perf_counter()
        v = self._verify(state, action, snapshot)
        return Verdict(v[0], v[1], v[2], (time.perf_counter() - t0) * 1000)

    def _verify(self, state, action, snapshot):
        if state not in self.signatures:
            return False, 'no_signature', ()
        els = _elements(snapshot)
        have = {}
        for e in els:
            have.setdefault(element_key(e, self.max_name), []).append(e)
        missing = tuple(sorted(k for k in self.signatures[state] if k not in have))
        if missing:
            return False, 'missing_elements', missing
        target = self.targets.get(action)
        if target is not None:
            found = have.get(target)
            if not found:
                return False, 'no_target', (target,)
            if not any(e.get('enabled', True) is not False for e in found):
                return False, 'target_disabled', (target,)
            if not any(not e.get('covered') for e in found if e.get('enabled', True) is not False):
                return False, 'target_covered', (target,)
        return True, None, ()

    def to_dict(self):
        return {'schema': DOM_SCHEMA, 'signatures': {s: sorted(map(list, k)) for s, k in sorted(self.signatures.items())},
                'targets': {a: list(t) for a, t in sorted(self.targets.items())}, 'max_name': self.max_name}

    @classmethod
    def from_dict(cls, data):
        if data.get('schema') != DOM_SCHEMA:
            raise ValueError(f'not a DOM verifier ({DOM_SCHEMA})')
        return cls({s: [tuple(k) for k in keys] for s, keys in data['signatures'].items()},
                   {a: tuple(t) for a, t in data['targets'].items()}, data.get('max_name', 32))


class VerifiedRouter:
    """Capture decides, DOM verifies (two steps). route(observation) first asks the wrapped Router; a fast action is then
    checked by the DomVerifier on observation['dom']. If they disagree, the answer is a hand-over with reason
    'verify_disagree' (detail = the verifier's reason), the router's episode expectation is cleared (as after any
    hand-over) and the observation is kept for relearning. Hand-overs of the wrapped router pass through unchanged.

    The wrapped router's monitor (if any) has already counted the route as a fast action; the verifier's hand-overs are
    counted here in `counts` and `verdicts`."""

    def __init__(self, router, verifier, dom_key='dom'):
        if not callable(getattr(router, 'route', None)):
            raise ValueError('router must be a simthinkd.Router')
        if not callable(getattr(verifier, 'verify', None)):
            raise ValueError('verifier must have verify(state, action, snapshot)')
        self.router, self.verifier, self.dom_key = router, verifier, dom_key
        self.counts = {'agree': 0, 'disagree': 0}
        self.last_verdict = None

    def reset(self, expect=None):
        self.router.reset(expect)

    def expect(self, states):
        self.router.expect(states)

    def route(self, observation):
        if not isinstance(observation, dict) or self.dom_key not in observation:
            raise ValueError(f"a verified route needs observation['{self.dom_key}']")
        route = self.router.route(observation)
        self.last_verdict = None
        if route.kind != 'action':
            return route
        verdict = self.verifier.verify(route.state, route.action, observation[self.dom_key])
        self.last_verdict = verdict
        if verdict.agree:
            self.counts['agree'] += 1
            return route
        self.counts['disagree'] += 1
        self.router.reset()  # same as after any hand-over: nothing is expected, the large model acts next
        self.router.handed_over.append(observation)
        return Route('handoff', route.state, route.confidence, None, VERIFY_DISAGREE, verdict.reason, None,
                     route.ms + verdict.ms, route.probabilities)
