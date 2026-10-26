"""Router kit (0.4.0): Router hand-over reasons, expected next states, SkillTable, HandoffMonitor, relearn, adapters.

    python -X utf8 tests/test_router.py        (NumPy only; relearn uses a stub trainer here, see test_router_example.py)
"""
import io
import json
import tempfile
import threading
from pathlib import Path

try:
    import pytest
except ImportError:  # CI runs this file as a script without pytest
    pytest = None

import numpy as np

import simthinkd
from simthinkd import (Decider, Decision, HandoffMonitor, PipelineAdapter, Route, Router, ScreenAdapter, Skill, SkillTable,
                       VectorAdapter, relearn)
from simthinkd.adapters import color_class, screen_tokens

STATES = Path(__file__).resolve().parent.parent / 'src' / 'simthinkd' / 'data' / 'doom_defend_states.json'
TABLE = {'LOGIN': ('FILL_LOGIN', ['PROFILE']), 'PROFILE': ('SUBMIT', ['ERROR', 'DONE']), 'ERROR': ('CLOSE', ['PROFILE']),
         'DONE': ('STOP', None, True)}


class Stub:
    """A decider that answers from a script: sentence -> (state, confidence). Unknown sentences: the sentence itself, 1.0."""

    def __init__(self, answers=None, sha='stub0', actions=None):
        self.answers, self.sha256 = dict(answers or {}), sha
        self.actions, self.preset = dict(actions or {}), {'goal': 'stub goal'}
        self.seen = []

    def decide(self, sentence):
        self.seen.append(sentence)
        state, p = self.answers.get(sentence, (sentence, 1.0))
        return Decision(state, p, {state: p}, 0.01)


def refused(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    return False


def walk(router, sentences):
    return [router.route(s) for s in sentences]


# ------------------------------------------------------------------ hand-over reasons
def test_fast_actions_along_the_expected_path():
    r = Router(Stub(), TABLE)
    r.reset(expect=['LOGIN'])
    routes = walk(r, ['LOGIN', 'PROFILE', 'ERROR', 'PROFILE', 'DONE'])
    assert [x.kind for x in routes] == ['action'] * 5
    assert [x.action for x in routes] == ['FILL_LOGIN', 'SUBMIT', 'CLOSE', 'SUBMIT', 'STOP']
    assert routes[1].expect == frozenset({'ERROR', 'DONE'}) and routes[-1].expect is None
    assert r.counts == {'action': 5}


def test_low_confidence_hands_over():
    r = Router(Stub({'s': ('LOGIN', 0.89)}), TABLE, tau=0.9)
    route = r.route('s')
    assert route.handoff and route.reason == 'low_confidence' and route.action is None and route.state == 'LOGIN'
    assert Router(Stub({'s': ('LOGIN', 0.9)}), TABLE, tau=0.9).route('s').kind == 'action'  # p >= tau is accepted


def test_unknown_state_hands_over():
    route = Router(Stub(), TABLE).route('LIST')  # confident, but this task has no skill for LIST
    assert route.handoff and route.reason == 'unknown_state'


def test_no_progress_same_state_after_a_fast_action():
    r = Router(Stub(), TABLE)
    a, b = walk(r, ['LOGIN', 'LOGIN'])  # the sign-in did nothing (a banner covered the button)
    assert a.kind == 'action'
    assert b.handoff and b.reason == 'no_progress' and b.detail == 'same_state'


def test_no_progress_unexpected_state_catches_a_confident_wrong_action():
    # the decider misread the screen as LOGIN and the fast action led to ERROR, which FILL_LOGIN never leads to
    r = Router(Stub(), TABLE)
    a, b = walk(r, ['LOGIN', 'ERROR'])
    assert a.kind == 'action' and b.handoff and b.reason == 'no_progress' and b.detail == 'unexpected_state'


def test_without_recorded_expectation_only_the_same_state_counts():
    r = Router(Stub(), {'A': 'GO', 'B': 'GO'})  # v2.1 rule: nothing recorded
    assert [x.kind for x in walk(r, ['A', 'B', 'A'])] == ['action'] * 3
    assert r.route('A').reason == 'no_progress'


def test_reasons_are_checked_in_order():
    r = Router(Stub({'x': ('LOGIN', 0.5)}), TABLE)
    r.route('LOGIN')
    assert r.route('x').reason == 'low_confidence'  # low confidence first, even where no-progress would also apply
    r.reset()
    r.route('LOGIN')
    assert r.route('LIST').reason == 'unknown_state'


def test_start_expectation_and_reset():
    r = Router(Stub(), TABLE)
    r.reset(expect='LOGIN')
    route = r.route('DONE')  # a run that "starts" on the done page: the v2.2 false-DONE case
    assert route.handoff and route.reason == 'no_progress' and route.detail == 'unexpected_state'
    r.reset()
    assert r.route('DONE').kind == 'action'  # no start expectation: accepted


def test_handoff_clears_the_expectation_and_expect_sets_it():
    r = Router(Stub({'low': ('PROFILE', 0.1)}), TABLE)
    walk(r, ['LOGIN', 'low'])
    assert r.route('LOGIN').kind == 'action'  # after a hand-over nothing is expected (the large model acted)
    r.reset()
    r.route('low')
    r.expect(['ERROR'])  # the caller knows what the large model's action should lead to
    assert r.route('PROFILE').reason == 'no_progress'


def test_final_skill_ends_the_checks():
    r = Router(Stub(), TABLE)
    walk(r, ['PROFILE', 'DONE'])
    assert r.check_progress('LOGIN') is None


def test_check_progress_has_no_side_effect():
    r = Router(Stub(), TABLE)
    r.route('LOGIN')
    assert r.check_progress('ERROR') == 'unexpected_state' and r.check_progress('LOGIN') == 'same_state'
    assert r.check_progress('PROFILE') is None and r.route('PROFILE').kind == 'action'


def test_deliberately_wrong_expected_state_is_caught():
    # negative control: plant a wrong expectation; the true next state must NOT be silently accepted
    wrong = SkillTable(TABLE)
    wrong.add('LOGIN', 'FILL_LOGIN', ['DONE'])  # wrong: signing in leads to PROFILE
    r = Router(Stub(), wrong)
    a, b = walk(r, ['LOGIN', 'PROFILE'])
    assert a.kind == 'action' and b.handoff and b.reason == 'no_progress' and b.detail == 'unexpected_state'
    right = Router(Stub(), TABLE)
    assert [x.kind for x in walk(right, ['LOGIN', 'PROFILE'])] == ['action', 'action']


def test_handed_over_observations_are_kept_for_relearning():
    r = Router(Stub({'u': ('LIST', 1.0)}), TABLE, keep=2)
    walk(r, ['LOGIN', 'u', 'LOGIN', 'u', 'u'])
    assert r.take_handed_over() == ['u', 'u'] and r.take_handed_over() == []


def test_router_refusals():
    assert refused(Router, Stub(), {})
    assert refused(Router, Stub(), TABLE, tau=0)
    assert refused(Router, Stub(), TABLE, tau=1.5)
    assert refused(Router, object(), TABLE)
    assert refused(Router, Stub(), TABLE, adapter='not callable')
    r = Router(Stub(), TABLE)
    assert refused(r.route, '') and refused(r.route, '   ') and refused(r.swap, object())
    assert refused(r.reset, expect=[''])
    assert refused(Router(Stub(), TABLE, adapter=lambda o: 42).route, 'x')


def test_router_on_a_real_decider_keeps_its_answers():
    # backward compatibility: routing never changes what the 0.3.0 decider chooses or how sure it is
    d = Decider('doom-defend')
    r = Router(d, {name: name for name in d.actions}, tau=0.9)
    rows = json.loads(STATES.read_text(encoding='utf8'))['rows'][:200]
    for row in rows:
        text = row['body']['state']['page']['text']
        plain, route = d.decide(text), r.route(text)
        assert route.state == plain.choice and abs(route.confidence - plain.confidence) <= 1e-9
        if route.kind == 'action':
            assert route.action == plain.choice and route.confidence >= 0.9
    assert sum(r.counts.values()) == len(rows)


def test_router_loads_a_decider_by_name():
    r = Router('doom-defend', {'TURN_LEFT': 'TURN_LEFT'})
    assert isinstance(r.decider, Decider)
    assert r.route('seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25').action == 'TURN_LEFT'


def test_hot_swap_under_concurrent_routing():
    old, new = Stub(sha='old'), Stub({'s': ('PROFILE', 1.0)}, sha='new')
    r = Router(old, TABLE)
    seen, errors = [], []

    def work():
        try:
            for _ in range(300):
                seen.append(r.route('s').state)
                r.reset()
        except Exception as error:  # noqa: BLE001 - any error fails the test below
            errors.append(error)
    threads = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in threads]
    assert r.swap(new) is old
    [t.join() for t in threads]
    assert not errors and set(seen) <= {'s', 'PROFILE'} and r.decider is new and r.route('s').state == 'PROFILE'


# ------------------------------------------------------------------ skill table
def test_skill_table_forms_and_equality():
    a = SkillTable(TABLE)
    b = SkillTable([(k, v) for k, v in TABLE.items()].__iter__())  # any iterable of pairs, read once
    c = SkillTable({'LOGIN': {'action': 'FILL_LOGIN', 'expect': ['PROFILE']}, 'PROFILE': Skill('SUBMIT', ('DONE', 'ERROR')),
                    'ERROR': ('CLOSE', 'PROFILE'), 'DONE': {'action': 'STOP', 'final': True}})
    assert a == b == c and len(a) == 4 and 'ERROR' in a and 'LIST' not in a
    assert a != SkillTable(dict(TABLE, ERROR=('CLOSE', ['DONE']))) and a != TABLE
    assert a.expected_after('PROFILE') == frozenset({'ERROR', 'DONE'}) and a.expected_after('DONE') is None
    assert a.get('LIST') is None and a.states() == ['LOGIN', 'PROFILE', 'ERROR', 'DONE']
    assert SkillTable() == SkillTable(None) == SkillTable(iter([])) and len(SkillTable()) == 0


def test_skill_table_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'skills.json'
        SkillTable(TABLE).save(path)
        assert SkillTable.load(path) == SkillTable(TABLE)
        path.write_text('{"skills": {}}', encoding='utf8')
        assert refused(SkillTable.load, path)


def test_skill_table_from_transitions():
    runs = [('LOGIN', 'FILL_LOGIN', 'PROFILE'), ('PROFILE', 'SUBMIT', 'ERROR'), ('ERROR', 'CLOSE', 'PROFILE'),
            ('PROFILE', 'SUBMIT', 'DONE'), ('DONE', 'STOP', None)]
    assert SkillTable.from_transitions(iter(runs)) == SkillTable(TABLE)
    assert len(SkillTable.from_transitions([])) == 0
    assert refused(SkillTable.from_transitions, runs + [('PROFILE', 'CLOSE', 'PROFILE')])  # two actions for one state
    assert refused(SkillTable.from_transitions, runs + [('DONE', 'STOP', 'LOGIN')])  # ended some runs and not others
    assert refused(SkillTable.from_transitions, [('LOGIN', 'FILL_LOGIN')])
    assert refused(SkillTable.from_transitions, [('', 'FILL_LOGIN', 'PROFILE')])


def test_skill_refusals():
    assert refused(Skill, '')
    assert refused(Skill, 'STOP', ['LOGIN'], True)  # a final skill has no next state
    assert refused(Skill, 'GO', [])  # an empty expectation cannot be checked
    assert refused(Skill, 'GO', [''])
    assert refused(SkillTable, {'': 'GO'})
    assert refused(SkillTable, {'A': 42})
    assert Skill('GO', 'B') == Skill('GO', ['B']) and Skill('GO', 'B').expect == frozenset({'B'})


# ------------------------------------------------------------------ hand-over monitor (relearning trigger)
def test_monitor_fires_on_the_handoff_rate_of_a_full_window():
    m = HandoffMonitor(window=4, rate=0.5, no_progress=3)
    assert [m.add(x) for x in [None, 'low_confidence', None]] == [False] * 3  # window not full yet
    assert m.add('unknown_state') is True and m.fired_at == 4 and m.handoff_rate == 0.5
    assert m.add(None) is True  # stays fired until reset
    m.reset()
    assert not m.fired and m.count == 0 and m.handoff_rate == 0.0


def test_monitor_below_threshold_does_not_fire():
    m = HandoffMonitor(window=10, rate=0.5, no_progress=3)
    for i in range(50):
        m.add('low_confidence' if i % 3 == 0 else None)  # about one in three: below 0.5
    assert not m.fired and m.fired_at is None and m.count == 50


def test_monitor_fires_on_no_progress_count_at_a_low_rate():
    m = HandoffMonitor(window=10, rate=0.5, no_progress=3)
    for reason in [None] * 7 + ['no_progress'] * 3:
        m.add(reason)
    assert m.fired_at == 10 and m.handoff_rate == 0.3 and m.no_progress_count == 3


def test_monitor_takes_routes_and_matches_the_sealed_v22_defaults():
    m = HandoffMonitor()
    assert (m.window, m.rate, m.no_progress) == (10, 0.5, 3)
    r = Router(Stub({'low': ('LOGIN', 0.2)}), TABLE, monitor=m)
    for _ in range(10):
        r.route('low')
    assert m.fired_at == 10 and m.state()['handoff_rate'] == 1.0


def test_monitor_refusals():
    assert refused(HandoffMonitor, window=0) and refused(HandoffMonitor, rate=0) and refused(HandoffMonitor, rate=1.2)
    assert refused(HandoffMonitor, no_progress=0) and refused(HandoffMonitor().add, 'bored')


# ------------------------------------------------------------------ relearn (stub trainer: no PyTorch needed)
def fake_trainer(calls):
    def train(examples, actions, goal, out, steps, seed, name, quiet):
        calls.append({'examples': list(examples), 'actions': dict(actions), 'goal': goal, 'out': out, 'steps': steps, 'seed': seed})
        return Stub({e[0]: (e[1], 1.0) for e in examples}, sha=f'new{len(calls)}', actions=actions)
    return train


def fired_router(**kwargs):
    r = Router(Stub({'B1': ('LOGIN', 0.3), 'B2': ('LOGIN', 0.4)}, sha='old', actions={'LOGIN': 'Sign-in form'}), TABLE,
               monitor=HandoffMonitor(window=2), **kwargs)
    walk(r, ['B1', 'B2'])
    assert r.monitor.fired
    return r


def test_relearn_teaches_retrains_swaps_and_logs():
    calls = []
    r = fired_router()
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / 'relearn.jsonl'
        teacher = {'B1': 'PROFILE', 'B2': 'LOGIN', 'B3': None}.get
        rep = relearn(r, teacher, iter(r.take_handed_over() + ['B3']), base_examples=iter([('A1', 'LOGIN')]),
                      out=Path(tmp) / 'm', log=log, trainer=fake_trainer(calls))
        line = json.loads(log.read_text(encoding='utf8'))
        assert rep.teacher_calls == 3 and rep.teacher_skipped == 1 and rep.new_examples == 2 and rep.examples == 3
        assert calls[0]['examples'] == [('A1', 'LOGIN'), ('B1', 'PROFILE'), ('B2', 'LOGIN')]
        assert calls[0]['actions']['LOGIN'] == 'Sign-in form' and 'PROFILE' in calls[0]['actions']  # old descriptions kept
        assert calls[0]['goal'] == 'stub goal' and calls[0]['steps'] == 600 and calls[0]['seed'] == 31
        assert r.decider.sha256 == 'new1' and rep.old_sha256 == 'old' and rep.new_sha256 == 'new1'
        assert line['schema'] == 'simthinkd-relearn/1' and line['trigger']['fired_at'] == 2 and not line['trigger']['forced']
        assert line['labels'] == ['LOGIN', 'PROFILE'] and not r.monitor.fired  # monitor reset after the swap
        assert r.route('B1').state == 'PROFILE'  # the swapped decider answers
        relearn(r, teacher, ['B1'], out=Path(tmp) / 'm2', log=log, trainer=fake_trainer(calls), force=True)
        assert len(log.read_text(encoding='utf8').splitlines()) == 2  # appended, never overwritten


def test_relearn_refuses_before_the_trigger_unless_forced():
    calls = []
    r = Router(Stub(sha='old'), TABLE, monitor=HandoffMonitor())
    assert refused(relearn, r, lambda o: 'LOGIN', ['x'], trainer=fake_trainer(calls))
    assert not calls and r.decider.sha256 == 'old'
    rep = relearn(r, lambda o: 'LOGIN', ['x'], trainer=fake_trainer(calls), force=True, out='unused')
    assert rep.trigger['forced'] and r.decider.sha256 == 'new1'
    no_monitor = Router(Stub(), TABLE)  # without a monitor the caller decides when
    assert relearn(no_monitor, lambda o: 'LOGIN', ['x'], trainer=fake_trainer(calls), out='unused').new_examples == 1


def test_relearn_refusals_leave_the_router_unchanged():
    calls = []
    r = fired_router()
    assert refused(relearn, r, lambda o: 'LOGIN', [], trainer=fake_trainer(calls))
    assert refused(relearn, r, lambda o: None, ['B1'], trainer=fake_trainer(calls))  # teacher skipped everything
    assert refused(relearn, r, lambda o: 7, ['B1'], trainer=fake_trainer(calls))
    assert refused(relearn, r, 'not callable', ['B1'], trainer=fake_trainer(calls))
    assert refused(relearn, r, lambda o: 'LOGIN', ['B1'], base_examples=['bad'], trainer=fake_trainer(calls))
    labels = [f'S{i}' for i in range(9)]  # nine labels: more than a decider can hold
    assert refused(relearn, r, lambda o: labels[int(o)], [str(i) for i in range(9)], trainer=fake_trainer(calls))

    def broken(*a, **k):
        raise RuntimeError('training failed')
    try:
        relearn(r, lambda o: 'LOGIN', ['B1'], trainer=broken)
    except RuntimeError:
        pass
    assert not calls and r.decider.sha256 == 'old' and r.monitor.fired  # nothing swapped, trigger still pending


def test_relearn_merges_new_skills_and_uses_the_adapter():
    calls = []
    r = Router(Stub(sha='old'), TABLE, adapter=lambda o: o['text'], monitor=HandoffMonitor(window=1))
    r.route({'text': 'LIST'})
    rep = relearn(r, lambda o: o['label'], [{'text': 'screen b', 'label': 'LOGIN'}], trainer=fake_trainer(calls),
                  skills={'LOGIN': ('FILL_LOGIN_B', ['PROFILE'])})
    assert calls[0]['examples'] == [('screen b', 'LOGIN')] and rep.new_examples == 1
    assert r.skills['LOGIN'].action == 'FILL_LOGIN_B' and r.skills['DONE'].final


# ------------------------------------------------------------------ adapters
def v21_screen_tokens_reference(rgb):
    """Experiment v2.1 feature (exp/harness.py screen_tokens), with PIL, for parity on sizes that divide evenly."""
    from PIL import Image
    im = Image.fromarray(rgb).resize((64, 48), Image.BOX)
    px = im.load()
    toks = []
    for cy in range(6):
        for cx in range(8):
            cells = [px[x, y] for y in range(cy * 8, cy * 8 + 8) for x in range(cx * 8, cx * 8 + 8)]
            mean = tuple(sum(c[i] for c in cells) // 64 for i in range(3))
            toks.append(f'g{cy}{cx}{color_class(*mean)}')
            sat = [s for s in (color_class(*c) for c in cells) if s in 'yorgbn']
            if len(sat) >= 4:
                counts = {s: sat.count(s) for s in sat}
                top = max(counts.values())
                toks.append(f'a{cy}{cx}' + (max(counts, key=counts.get) if list(counts.values()).count(top) == 1 else '?'))
    return toks


def random_screen(rng, h, w):
    img = np.full((h, w, 3), 245, np.uint8)
    for _ in range(12):
        y, x = rng.integers(0, h - 40), rng.integers(0, w - 60)
        img[y:y + rng.integers(10, 120), x:x + rng.integers(10, 200)] = rng.integers(0, 256, 3)
    return img


def test_screen_tokens_match_the_v21_feature():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print('SKIP v2.1 parity (Pillow not installed)')
        return
    rng = np.random.default_rng(0)
    for h, w in [(768, 1024), (192, 256), (480, 640)] * 4:
        img = random_screen(rng, h, w)
        mine, ref = screen_tokens(img).split(), v21_screen_tokens_reference(img)
        assert len(mine) == len(ref)
        assert all(a == b for a, b in zip(mine, ref) if not b.endswith('?'))  # v2.1 broke ties at random; skip those


def test_screen_adapter_sentence():
    white = np.full((48, 64, 3), 250, np.uint8)
    assert screen_tokens(white) == ' '.join(f'g{r}{c}w' for r in range(6) for c in range(8))
    img = white.copy()
    img[0:8, 0:8] = (220, 30, 30)  # one red cell
    s = ScreenAdapter()({'pixels': img, 'title': 'Sign in', 'prev': None})
    assert s.startswith('title: Sign in | prev: START | screen: g00r a00r g01w')
    assert ScreenAdapter(with_title=False, with_prev=False)(img) == 'screen: ' + screen_tokens(img)
    assert ScreenAdapter(cols=4, rows=3)(white).count('g') == 12
    odd = np.full((100, 130, 3), 250, np.uint8)  # sizes that do not divide evenly still work (area average)
    assert screen_tokens(odd) == screen_tokens(white)


def test_screen_adapter_refusals():
    assert refused(screen_tokens, np.zeros((40, 64, 3), np.uint8))  # smaller than the grid needs
    assert refused(screen_tokens, np.zeros((48, 64), np.uint8))
    assert refused(ScreenAdapter, cols=11)
    assert refused(ScreenAdapter(), {'title': 'no pixels'})


def test_pipeline_adapter_sentence():
    a = PipelineAdapter()
    obs = {'step': 'draft', 'request': {'pages': 12, 'kind': 'proposal', 'lang': 'ko', 'urgent': True},
           'gate': {'name': 'g_ko_word', 'verdict': 'fail', 'reasons': ['word_pan', 'length long', 'x', 'y', 'z', 'w']}}
    assert a(obs) == ('step: draft | request: kind proposal ; lang ko ; pages 12 ; urgent yes | gate: g_ko_word FAIL | '
                      'reasons: word_pan ; length long ; x ; y ; z')
    assert PipelineAdapter(fields=['lang', 'kind', 'missing'])(obs).startswith('step: draft | request: lang ko ; kind proposal | gate')
    assert a({}) == 'step: - | request: none | gate: none'
    assert a({'request': {'tags': ['b', 'a']}}) == 'step: - | request: tags ["b","a"] | gate: none'
    assert refused(a, 'text') and refused(a, {'request': [1]}) and refused(a, {'gate': 'FAIL'})
    assert refused(PipelineAdapter, fields='kind') and refused(PipelineAdapter, max_reasons=-1)


def test_vector_adapter_sentence():
    a = VectorAdapter([0, 2], names=['base_vx', 'yaw_rate'])
    assert a([0.42, 9.0, -1.0]) == 'obs: base_vx q5 | yaw_rate q0'
    assert a(np.array([2.0, 0.0, 1.0])) == 'obs: base_vx q7 | yaw_rate q7'  # clipped to the range, top bin inclusive
    b = VectorAdapter([1], low=[0.0], high=[10.0], levels=2, prefix='robot')
    assert b([0, 4.99]) == 'robot: x1 q0' and b([0, 5.0]) == 'robot: x1 q1'
    assert refused(a, [0.1]) and refused(a, [float('nan'), 0, 0]) and refused(a, [0, 0, float('inf')])
    assert refused(VectorAdapter, []) and refused(VectorAdapter, [1, 1]) and refused(VectorAdapter, [-1])
    assert refused(VectorAdapter, [0], names=['two words']) and refused(VectorAdapter, [0, 1], names=['one'])
    assert refused(VectorAdapter, [0], low=1, high=1) and refused(VectorAdapter, [0], levels=1)


def test_same_router_different_inputs():
    # one decider and one skill table; only the adapter changes per kind of observation
    for adapter, obs in [(ScreenAdapter(), {'pixels': np.full((48, 64, 3), 250, np.uint8), 'title': 'T'}),
                         (PipelineAdapter(), {'step': 'lint', 'gate': {'name': 'g', 'verdict': 'PASS'}}),
                         (VectorAdapter([0, 1]), [0.1, -0.3])]:
        stub = Stub({adapter(obs): ('LOGIN', 0.99)})
        route = Router(stub, TABLE, adapter=adapter).route(obs)
        assert route.action == 'FILL_LOGIN' and stub.seen == [adapter(obs)]


# ------------------------------------------------------------------ backward compatibility
def test_public_api_of_030_is_unchanged():
    for name in ['Decider', 'Decision', 'Score', 'Scorer', 'available', 'build_request', 'fit', 'fit_score', '__version__']:
        assert name in simthinkd.__all__ and hasattr(simthinkd, name)
    assert simthinkd.__version__ == '0.5.0'
    d = Decider('doom-defend')
    assert d.decide('seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25').choice == 'TURN_LEFT'
    assert str(Route('action', 'A', 0.5, 'GO')).startswith('GO [A 50%')


CASES = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]

if __name__ == '__main__':  # CI runs test files as scripts
    for f in CASES:
        f()
    print(f'router tests: {len(CASES)} passed')
