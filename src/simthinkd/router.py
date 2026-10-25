"""Router: SimThink D decides when it safely can, and hands the case over (to a large model or a person) when it should not.

    from simthinkd import Decider, Router, SkillTable
    skills = SkillTable({'LOGIN': ('FILL_LOGIN', ['PROFILE']),        # state -> (action, expected next states)
                         'PROFILE': ('SUBMIT', ['ERROR', 'DONE']),
                         'ERROR': ('CLOSE', ['PROFILE']),
                         'DONE': ('STOP', None, True)})               # final: the episode ends here
    router = Router(Decider('models/screen'), skills, tau=0.9)
    router.reset(expect=['LOGIN'])                                   # a new episode starts on the sign-in screen
    route = router.route('title: Sign in | prev: START | screen: g00w ...')
    route.kind, route.action, route.reason                           # ('action', 'FILL_LOGIN', None) or ('handoff', None, 'low_confidence')

The decider names the current state (or the next action, if you trained it that way); the skill table holds, per state,
the scripted action and the state(s) that action is expected to lead to. A route is a fast action only if all three hold:
the decider is confident (p >= tau), the state is in the table, and the state is one the previous fast action was expected
to lead to. Otherwise it is a hand-over with one reason:

    low_confidence  p < tau
    unknown_state   the state has no skill in this table (it belongs to another task, or the screen was never learned)
    no_progress     the observed state is not an expected next state of the previous fast action
                    (detail 'same_state': the action had no effect; 'unexpected_state': it led somewhere else)

The no-progress check is what catches a confident wrong action at the very next observation: a small classifier can be
sure and wrong on a screen it has never seen, and a confidence threshold alone does not stop that. When a skill has no
recorded expectation, the check falls back to "the same state again after a fast action" (the rule of experiment v2.1).
"""
import json
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path

LOW_CONFIDENCE = 'low_confidence'
UNKNOWN_STATE = 'unknown_state'
NO_PROGRESS = 'no_progress'
REASONS = (LOW_CONFIDENCE, UNKNOWN_STATE, NO_PROGRESS)
SKILLS_SCHEMA = 'simthinkd-skills/1'


def _name(value, what):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{what} must be a non-empty string (got {value!r})')
    return value


def _states(values, what):
    if values is None:
        return None
    if isinstance(values, str):
        values = [values]
    return frozenset(_name(v, what) for v in values)


@dataclass(frozen=True)
class Skill:
    """What to do in one state: the scripted action, the state(s) it should lead to, and whether it ends the episode.

    expect=None means "not recorded" (the router then only checks that the state changed); an empty set is refused,
    because a non-final action that may lead nowhere cannot be checked."""
    action: str
    expect: frozenset = None
    final: bool = False

    def __post_init__(self):
        _name(self.action, 'a skill action')
        expect = _states(self.expect, 'an expected state')
        if self.final and expect:
            raise ValueError(f'final skill {self.action!r} ends the episode, so it has no expected next state')
        if expect is not None and not expect and not self.final:
            raise ValueError(f'skill {self.action!r}: give at least one expected next state, or None if not recorded')
        object.__setattr__(self, 'expect', None if self.final else expect)
        object.__setattr__(self, 'final', bool(self.final))

    def to_dict(self):
        return {'action': self.action, 'expect': None if self.expect is None else sorted(self.expect), 'final': self.final}


def _skill(spec):
    if isinstance(spec, Skill):
        return spec
    if isinstance(spec, str):
        return Skill(spec)
    if isinstance(spec, dict):
        return Skill(spec.get('action'), spec.get('expect'), spec.get('final', False))
    if isinstance(spec, (tuple, list)) and 1 <= len(spec) <= 3:
        return Skill(*spec)
    raise ValueError(f'a skill is an action name, (action, expect[, final]), a dict or a Skill (got {spec!r})')


class SkillTable:
    """state -> Skill. Build it by hand, from a dict, or from observed transitions (`from_transitions`)."""

    def __init__(self, entries=None):
        self._skills = {}
        items = entries.items() if hasattr(entries, 'items') else (entries or ())
        for state, spec in items:  # any iterable of (state, spec) pairs is read once
            self.add(state, spec)

    def add(self, state, action, expect=None, final=False):
        """Add or replace the skill of one state. `action` may also be a full skill spec (see the class doc)."""
        skill = Skill(action, expect, final) if isinstance(action, str) else _skill(action)
        self._skills[_name(state, 'a state')] = skill
        return skill

    @classmethod
    def from_transitions(cls, transitions):
        """Learn the table from (state, action, next_state) triples, e.g. the steps of successful teacher runs.

        next_state None means the action ended the run (final). A state seen with two different actions, or ending some
        runs and not others, is refused: the table must be one fixed script per state."""
        actions, nexts, ends = {}, {}, {}
        for i, item in enumerate(transitions):
            try:
                state, action, nxt = item
            except (TypeError, ValueError):
                raise ValueError(f'transition {i}: expected (state, action, next_state), got {item!r}') from None
            _name(state, f'transition {i} state')
            _name(action, f'transition {i} action')
            if actions.setdefault(state, action) != action:
                raise ValueError(f'state {state!r} was followed by two actions: {actions[state]!r} and {action!r}')
            ends.setdefault(state, set()).add(nxt is None)
            if nxt is not None:
                nexts.setdefault(state, set()).add(_name(nxt, f'transition {i} next state'))
        table = cls()
        for state, action in actions.items():
            if len(ends[state]) > 1:
                raise ValueError(f'state {state!r}: action {action!r} ended some runs and not others')
            final = ends[state] == {True}
            table.add(state, Skill(action, None if final else nexts[state], final))
        return table

    def get(self, state):
        return self._skills.get(state)

    def expected_after(self, state):
        """Expected next states of the skill of `state` (None: not recorded or final, KeyError: no skill)."""
        return self._skills[state].expect

    def update(self, other):
        for state, skill in (other.items() if hasattr(other, 'items') else other):
            self.add(state, skill)
        return self

    def items(self):
        return self._skills.items()

    def states(self):
        return list(self._skills)

    def to_dict(self):
        return {state: skill.to_dict() for state, skill in self._skills.items()}

    def save(self, path):
        Path(path).write_text(json.dumps({'schema': SKILLS_SCHEMA, 'skills': self.to_dict()}, ensure_ascii=False, indent=1),
                              encoding='utf8')

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf8'))
        if data.get('schema') != SKILLS_SCHEMA:
            raise ValueError(f'{path} is not a skill table ({SKILLS_SCHEMA})')
        return cls(data['skills'])

    def __getitem__(self, state):
        return self._skills[state]

    def __contains__(self, state):
        return state in self._skills

    def __iter__(self):
        return iter(self._skills)

    def __len__(self):
        return len(self._skills)

    def __eq__(self, other):
        return isinstance(other, SkillTable) and self._skills == other._skills

    def __repr__(self):
        return f'SkillTable({len(self)} states: {", ".join(self._skills)})'


@dataclass(frozen=True)
class Route:
    """The router's answer: kind 'action' (do `action` now) or 'handoff' (ask the large model; `reason` says why)."""
    kind: str
    state: str
    confidence: float
    action: str = None
    reason: str = None
    detail: str = None
    expect: frozenset = None
    ms: float = 0.0
    probabilities: dict = field(default=None, repr=False, compare=False)

    @property
    def handoff(self):
        return self.kind == 'handoff'

    def __str__(self):
        what = self.action if self.kind == 'action' else f'HANDOFF {self.reason}' + (f' ({self.detail})' if self.detail else '')
        return f'{what} [{self.state} {self.confidence:.0%}, {self.ms:.2f} ms]'


class HandoffMonitor:
    """Relearning trigger over the last `window` routes: fires when the hand-over rate reaches `rate`, or when at least
    `no_progress` of them were no-progress hand-overs. It looks only at full windows and stays fired until reset().
    The defaults are the values sealed in experiment v2.2 (10, 0.5, 3)."""

    def __init__(self, window=10, rate=0.5, no_progress=3):
        if not isinstance(window, int) or window < 1:
            raise ValueError('window must be a positive whole number')
        if not 0 < rate <= 1:
            raise ValueError('rate must be in (0, 1]')
        if not isinstance(no_progress, int) or no_progress < 1:
            raise ValueError('no_progress must be a positive whole number')
        self.window, self.rate, self.no_progress = window, rate, no_progress
        self.reset()

    def reset(self):
        self._hist = deque(maxlen=self.window)
        self.count, self.fired_at = 0, None

    def add(self, route):
        """Record one route (a Route, or its hand-over reason: None for a fast action). Returns True once fired."""
        reason = route.reason if isinstance(route, Route) else route
        if reason is not None and reason not in REASONS:
            raise ValueError(f'unknown hand-over reason {reason!r}')
        self.count += 1
        self._hist.append(reason)
        if self.fired_at is None and len(self._hist) == self.window:
            if self.handoff_rate >= self.rate or self.no_progress_count >= self.no_progress:
                self.fired_at = self.count
        return self.fired

    @property
    def fired(self):
        return self.fired_at is not None

    @property
    def handoff_rate(self):
        return sum(r is not None for r in self._hist) / len(self._hist) if self._hist else 0.0

    @property
    def no_progress_count(self):
        return sum(r == NO_PROGRESS for r in self._hist)

    def state(self):
        return {'window': self.window, 'rate': self.rate, 'no_progress': self.no_progress, 'routes': self.count,
                'fired_at': self.fired_at, 'handoff_rate': round(self.handoff_rate, 4),
                'no_progress_count': self.no_progress_count}


class Router:
    """A decider plus a skill table: route(observation) -> Route. One router follows one episode at a time (reset()
    starts a new one); route() and swap() are safe to call from several threads."""

    def __init__(self, decider, skills, tau=0.9, adapter=None, monitor=None, keep=1000):
        if isinstance(decider, (str, Path)):
            from .core import Decider
            decider = Decider(str(decider))
        if not callable(getattr(decider, 'decide', None)):
            raise ValueError('decider must have a decide(sentence) method (a simthinkd.Decider)')
        self.skills = skills if isinstance(skills, SkillTable) else SkillTable(skills)
        if not len(self.skills):
            raise ValueError('a router needs at least one skill')
        if not 0 < tau <= 1:
            raise ValueError('tau must be in (0, 1]')
        if adapter is not None and not callable(adapter):
            raise ValueError('adapter must be callable: observation -> sentence')
        self.decider, self.tau, self.adapter, self.monitor = decider, float(tau), adapter, monitor
        self.counts = Counter()
        self.handed_over = deque(maxlen=keep)  # observations sent to the large model, for relearning
        self._lock = threading.RLock()
        self._last, self._expect = None, None

    def sentence(self, observation):
        text = self.adapter(observation) if self.adapter else observation
        if not isinstance(text, str) or not text.strip():
            raise ValueError('the observation (after the adapter) must be a non-empty sentence')
        return text

    def reset(self, expect=None):
        """Start a new episode. `expect`: the state(s) the episode should start in (checked like a next state)."""
        with self._lock:
            self._last, self._expect = None, _states(expect, 'an expected state')

    def expect(self, states):
        """Declare the state(s) the next observation should show, e.g. after the large model acted on a hand-over."""
        with self._lock:
            self._expect = _states(states, 'an expected state')

    def check_progress(self, state):
        """None if `state` is fine after the last fast action, else 'same_state' or 'unexpected_state'. No side effect."""
        with self._lock:
            expect, last = self._expect, self._last
        if expect is not None:
            if state in expect:
                return None
            return 'same_state' if last is not None and state == last else 'unexpected_state'
        if last is not None and state == last:  # nothing recorded: v2.1 rule, the same state again means no progress
            return 'same_state'
        return None

    def route(self, observation):
        text = self.sentence(observation)
        with self._lock:
            start = time.perf_counter()
            decision = self.decider.decide(text)
            state, p = decision.choice, float(decision.confidence)
            skill = self.skills.get(state)
            reason = detail = None
            if p < self.tau:
                reason = LOW_CONFIDENCE
            elif skill is None:
                reason = UNKNOWN_STATE
            else:
                detail = self.check_progress(state)
                reason = NO_PROGRESS if detail else None
            ms = (time.perf_counter() - start) * 1000
            if reason:
                self._last, self._expect = None, None
                route = Route('handoff', state, p, None, reason, detail, None, ms, decision.probabilities)
                self.handed_over.append(observation)
            else:
                self._last = None if skill.final else state
                self._expect = skill.expect
                route = Route('action', state, p, skill.action, None, None, skill.expect, ms, decision.probabilities)
            self.counts[reason or 'action'] += 1
            if self.monitor is not None:
                self.monitor.add(route)
            return route

    def swap(self, decider):
        """Hot-swap the decider (e.g. after relearning). Routes in flight finish on the old one. Returns the old one."""
        if not callable(getattr(decider, 'decide', None)):
            raise ValueError('decider must have a decide(sentence) method (a simthinkd.Decider)')
        with self._lock:
            old, self.decider = self.decider, decider
        return old

    def take_handed_over(self):
        """The observations handed over since the last call (oldest first); the buffer is emptied."""
        with self._lock:
            out = list(self.handed_over)
            self.handed_over.clear()
        return out

    def __repr__(self):
        return f'Router({self.decider!r}, {len(self.skills)} skills, tau={self.tau})'
