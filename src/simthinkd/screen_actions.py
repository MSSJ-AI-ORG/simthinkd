"""Screen actions: small guards that make fast screen control faster and safer, with no site-specific values inside.

They come from a live shopping-site run where four changes cut one mission from 80.8 s to 29.2 s (12/12 runs succeeded):
press lightly instead of moving a human-like cursor, open a result link by its address instead of clicking its card,
use a rule where one is known before asking the decider, and judge success from page text. Every site value (band
heights, link patterns, success words) is passed in by the caller.

    from simthinkd import NoClickBands, ExpectAfter, open_or_press, RuleFirst, PageTextCheck
    bands = NoClickBands(top=345, bottom_from=940)          # fixed header / footer that the accessibility tree misses
    bands.allows((640, 300))                                 # False: inside the header band
    kind, value = open_or_press(element)                     # ('open', 'https://...') for a link, ('press', (x, y)) otherwise
    done = ExpectAfter(read_state, timeout=5.0)              # after pressing, the expected screen must appear in time
    ok, state, ms = done.wait({'PRODUCT'})
    rules = RuleFirst([(lambda snap: has_cart_button(snap), 'ADD_TO_CART')], fallback=router.route)
    check = PageTextCheck(words=['added to cart'], count=lambda text: cart_count(text))
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

__all__ = ['NoClickBands', 'ExpectAfter', 'open_or_press', 'RuleFirst', 'RuleRoute', 'PageTextCheck']


class NoClickBands:
    """Screen bands where no click may land: fixed headers and footers that cover the page but are missing from the
    accessibility tree, so a click aimed at a page element below them would hit them instead.

    top: band from y=0 to `top` (exclusive). bottom_from: band from `bottom_from` to the bottom. left / right likewise.
    Each is optional. `allows(point)` is False when the point is inside any band."""

    def __init__(self, top=None, bottom_from=None, left=None, right_from=None):
        for name, v in (('top', top), ('bottom_from', bottom_from), ('left', left), ('right_from', right_from)):
            if v is not None and (not isinstance(v, (int, float)) or v < 0):
                raise ValueError(f'{name} must be a non-negative number or None')
        self.top, self.bottom_from, self.left, self.right_from = top, bottom_from, left, right_from

    def allows(self, point):
        x, y = float(point[0]), float(point[1])
        if self.top is not None and y < self.top:
            return False
        if self.bottom_from is not None and y >= self.bottom_from:
            return False
        if self.left is not None and x < self.left:
            return False
        if self.right_from is not None and x >= self.right_from:
            return False
        return True

    def visible_part(self, element):
        """Centre of the part of an element (x, y, w, h) that lies outside the bands, or None if nothing is left."""
        x, y, w, h = (float(element[k]) for k in ('x', 'y', 'w', 'h'))
        x0, y0, x1, y1 = x, y, x + w, y + h
        if self.top is not None:
            y0 = max(y0, self.top)
        if self.bottom_from is not None:
            y1 = min(y1, self.bottom_from)
        if self.left is not None:
            x0 = max(x0, self.left)
        if self.right_from is not None:
            x1 = min(x1, self.right_from)
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0 + x1) / 2, (y0 + y1) / 2


def open_or_press(element, allow=None):
    """How to act on one element: ('open', href) when it is a plain link with an http(s) address, else
    ('press', (x, y)) at its centre. `allow(href)` may refuse an address (e.g. a different site): then it is pressed.
    Opening the address skips the slowest step seen in practice: waiting for a card click to open a new tab."""
    href = element.get('href') if isinstance(element, dict) else None
    if isinstance(href, str) and re.match(r'^https?://', href) and (allow is None or allow(href)):
        return 'open', href
    x, y, w, h = (float(element.get(k, 0)) for k in ('x', 'y', 'w', 'h'))
    return 'press', (x + w / 2, y + h / 2)


class ExpectAfter:
    """After an action, waits until one of the expected states appears, or gives up after `timeout` seconds.

    read_state(): returns the current state name (or None while loading). `wait(expected)` returns
    (ok, last_state, ms). A miss is a failed step: the caller undoes what its own action opened and hands the case over."""

    def __init__(self, read_state, timeout=5.0, poll=0.1, clock=time.monotonic, sleep=time.sleep):
        if timeout <= 0 or poll <= 0:
            raise ValueError('timeout and poll must be positive')
        self.read_state, self.timeout, self.poll, self.clock, self.sleep = read_state, timeout, poll, clock, sleep

    def wait(self, expected):
        expected = set(expected)
        if not expected:
            raise ValueError('expected must name at least one state')
        start = self.clock()
        state = None
        while True:
            state = self.read_state()
            if state in expected:
                return True, state, (self.clock() - start) * 1000.0
            if self.clock() - start >= self.timeout:
                return False, state, (self.clock() - start) * 1000.0
            self.sleep(self.poll)


@dataclass
class RuleRoute:
    kind: str            # 'rule' or the fallback's kind
    action: str = None
    rule: int = None     # index of the rule that fired
    fallback: object = None


class RuleFirst:
    """Known rules before the decider. rules: list of (predicate(observation) -> bool, action). The first predicate that
    holds gives the action; if none holds, `fallback(observation)` (e.g. Router.route) decides. A predicate that raises
    counts as not holding, so a broken rule never blocks the fallback."""

    def __init__(self, rules, fallback):
        self.rules = [(p, str(a)) for p, a in rules]
        for p, _ in self.rules:
            if not callable(p):
                raise ValueError('each rule is (callable predicate, action)')
        if not callable(fallback):
            raise ValueError('fallback must be callable')
        self.fallback = fallback

    def route(self, observation):
        for i, (pred, action) in enumerate(self.rules):
            try:
                hit = bool(pred(observation))
            except Exception:
                hit = False
            if hit:
                return RuleRoute('rule', action, i)
        r = self.fallback(observation)
        return RuleRoute(getattr(r, 'kind', 'fallback'), getattr(r, 'action', None), None, r)


class PageTextCheck:
    """Success from page text, not from the screenshot. words: any of them in the page text means success.
    count(text) -> int or None: a counter on the page (e.g. items in a basket); success when it grew from the start."""

    def __init__(self, words=(), count=None):
        self.words = tuple(' '.join(str(w).lower().split()) for w in words if str(w).strip())
        if not self.words and count is None:
            raise ValueError('give success words, a counter, or both')
        self.count = count
        self.start = None

    def begin(self, text):
        self.start = self.count(text) if self.count else None
        return self.start

    def done(self, text):
        t = ' '.join(str(text or '').lower().split())
        if any(w in t for w in self.words):
            return True
        if self.count and self.start is not None:
            n = self.count(text)
            return n is not None and n > self.start
        return False
