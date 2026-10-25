"""DOM input: DomAdapter, CombinedAdapter, DomVerifier, VerifiedRouter (NumPy only).

    python -X utf8 tests/test_dom_adapter.py
"""
import json
import random

import numpy as np

import simthinkd
from simthinkd import (CombinedAdapter, Decision, DomAdapter, DomVerifier, PopupGuard, Router, ScreenAdapter, SkillTable,
                       VerifiedRouter)
from simthinkd.dom_adapter import DOM_SNAPSHOT_JS, VERIFY_DISAGREE, element_key

SECRET = 'hunter2-secret-typed-value'


def refused(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    return False


def el(role, name, x=0, y=0, enabled=True, covered=False, **extra):
    d = {'role': role, 'name': name, 'enabled': enabled, 'covered': covered, 'x': x, 'y': y, 'w': 100, 'h': 40}
    d.update(extra)
    return d


FORM = {'title': 'Export - Demo Portal', 'path': '/index.html',
        'elements': [el('button', 'Submit request', 362, 615)]}
LOOKALIKE = {'title': 'Export - Demo Portal', 'path': '/index.html',
             'elements': [el('link', 'Continue to the form', 262, 300), el('button', 'Cancel request', 362, 615)]}
LOGIN = {'title': 'Sign in - Demo Portal', 'url': 'http://127.0.0.1:8765/index.html?task=T1&seed=5&user=demo#x',
         'elements': [el('textbox', 'Username', 362, 250, value=SECRET), el('textbox', '', 362, 330, value=SECRET),
                      el('button', 'Sign in', 362, 420)]}


class Stub:
    def __init__(self, answers):
        self.answers, self.seen = dict(answers), []

    def decide(self, sentence):
        self.seen.append(sentence)
        state, p = self.answers.get(sentence, ('UNSEEN', 0.2))
        return Decision(state, p, {state: p}, 0.01)


def test_dom_sentence_form():
    s = DomAdapter()({'dom': FORM, 'title': 'Export - Demo Portal', 'prev': 'CLOSE_DIALOG'})
    assert s == 'title: Export - Demo Portal | path: /index.html | prev: CLOSE_DIALOG | dom: button submit_request'
    assert DomAdapter()(FORM).endswith('prev: START | dom: button submit_request')
    flags = DomAdapter(with_title=False, with_path=False, with_prev=False)(
        {'elements': [el('button', 'Pay', enabled=False), el('button', 'Close', y=50, covered=True)]})
    assert flags == 'dom: button pay disabled ; button close covered'
    assert DomAdapter()({'elements': []}).endswith('dom: none')


def test_dom_order_is_deterministic():
    els = [el('button', f'b{i}', x=random.Random(i).randint(0, 1000), y=random.Random(i + 99).randint(0, 700)) for i in range(20)]
    a = DomAdapter()({'title': 't', 'elements': els})
    for k in range(10):
        shuffled = els[:]
        random.Random(k).shuffle(shuffled)
        assert DomAdapter()({'title': 't', 'elements': shuffled}) == a
    # reading order: top to bottom, then left to right
    s = DomAdapter(with_title=False, with_path=False, with_prev=False)(
        {'elements': [el('button', 'right', x=500, y=10), el('button', 'down', x=0, y=300), el('button', 'left', x=10, y=12)]})
    assert s == 'dom: button left ; button right ; button down'


def test_dom_length_is_bounded():
    els = [el('button', 'a very long button label number %d ' % i * 5, x=i, y=i * 9) for i in range(500)]
    s = DomAdapter(max_elements=32, max_name=32)({'title': 'x' * 1000, 'elements': els})
    body = s.split('dom: ', 1)[1].split(' ; ')
    assert len(body) == 32 and all(len(w) <= len('button ') + 32 for w in body)
    assert len(s) < 32 * 45 + 300
    assert refused(DomAdapter, max_elements=0) and refused(DomAdapter, max_name=0) and refused(DomAdapter, max_elements=1000)


def test_no_typed_values_or_query_leak():
    s = DomAdapter()({'dom': LOGIN, 'prev': None})
    assert SECRET.split('-')[0] not in s and 'secret' not in s
    assert 'seed' not in s and 'user=demo' not in s and '#x' not in s and 'path: /index.html' in s
    c = CombinedAdapter()({'pixels': np.full((48, 64, 3), 250, np.uint8), 'title': 'Sign in', 'dom': LOGIN})
    assert 'secret' not in c and 'hunter2' not in c
    v = DomVerifier.fit([('LOGIN', LOGIN)])
    assert 'hunter2' not in json.dumps(v.to_dict())
    # the in-page script never reads what a person typed
    assert '.value' not in DOM_SNAPSHOT_JS and 'innerHTML' not in DOM_SNAPSHOT_JS
    assert "getAttribute('value')" in DOM_SNAPSHOT_JS  # only the fixed label of <input type=submit|button>


def test_combined_is_the_union():
    px = np.zeros((48, 64, 3), np.uint8)
    px[:, :32] = (40, 140, 60)
    obs = {'pixels': px, 'title': 'Export - Demo Portal', 'prev': 'START', 'dom': FORM}
    screen, dom = ScreenAdapter()(obs), DomAdapter()(obs)
    both = CombinedAdapter()(obs)
    assert both.startswith(screen + ' | ')
    words = lambda s: set(s.replace('|', ' ').replace(';', ' ').split())
    assert words(both) == words(screen) | words(dom) - {'path:', '/index.html'}
    assert both.count('title:') == 1 and both.count('prev:') == 1
    assert refused(CombinedAdapter(), {'pixels': px}) and refused(CombinedAdapter(), FORM)


def test_lookalike_told_apart_only_with_dom():
    px = np.full((48, 64, 3), 238, np.uint8)
    px[36:42, 20:44] = (29, 138, 58)  # the same green button on both screens
    a = {'pixels': px, 'title': 'Export - Demo Portal', 'prev': 'START', 'dom': FORM}
    b = {'pixels': px.copy(), 'title': 'Export - Demo Portal', 'prev': 'START', 'dom': LOOKALIKE}
    screen = ScreenAdapter()
    assert screen(a) == screen(b)  # capture alone cannot tell them apart: any decider gives the same answer
    dom, both = DomAdapter(), CombinedAdapter()
    assert dom(a) != dom(b) and both(a) != both(b)
    skills = SkillTable({'FORM3': ('SUBMIT', ['DONE']), 'DONE': ('DONE', None, True)})
    cap = Router(Stub({screen(a): ('FORM3', 0.99)}), skills, adapter=screen)
    cap.reset(expect=['FORM3'])
    wrong = cap.route(b)
    assert wrong.kind == 'action' and wrong.action == 'SUBMIT'  # confident and wrong: it would press "Cancel request"
    dr = Router(Stub({dom(a): ('FORM3', 0.99)}), skills, adapter=dom)
    dr.reset(expect=['FORM3'])
    assert dr.route(b).kind == 'handoff'
    dr.reset(expect=['FORM3'])
    assert dr.route(a).action == 'SUBMIT'


def test_verifier_fit_and_reasons():
    v = DomVerifier.fit([('FORM3', FORM), ('FORM3', {'elements': FORM['elements'] + [el('button', 'Help', 900, 10)]}),
                         ('DONE', {'elements': []})], targets={'SUBMIT': ('button', 'Submit request')})
    assert v.signatures['FORM3'] == {('button', 'submit_request')} and v.signatures['DONE'] == frozenset()
    assert v.verify('FORM3', 'SUBMIT', FORM).agree
    assert v.verify('DONE', 'DONE', {'elements': []}).agree
    r = v.verify('FORM3', 'SUBMIT', LOOKALIKE)
    assert not r.agree and r.reason == 'missing_elements' and r.missing == (('button', 'submit_request'),) and r.ms >= 0
    assert v.verify('NOPE', 'SUBMIT', FORM).reason == 'no_signature'
    dis = {'elements': [el('button', 'Submit request', enabled=False)]}
    cov = {'elements': [el('button', 'Submit request', covered=True)]}
    w = DomVerifier({'FORM3': []}, {'SUBMIT': ('button', 'Submit request')})
    assert w.verify('FORM3', 'SUBMIT', dis).reason == 'target_disabled'
    assert w.verify('FORM3', 'SUBMIT', cov).reason == 'target_covered'
    assert w.verify('FORM3', 'SUBMIT', {'elements': []}).reason == 'no_target'
    half = DomVerifier.fit([('S', FORM), ('S', {'elements': []})], min_share=0.5)
    assert half.signatures['S'] == {('button', 'submit_request')}
    assert DomVerifier.from_dict(json.loads(json.dumps(v.to_dict()))).to_dict() == v.to_dict()
    assert refused(DomVerifier.fit, [], min_share=0) and refused(DomVerifier.from_dict, {'schema': 'x'})
    assert refused(v.verify, 'FORM3', 'SUBMIT', 'not a dict')
    assert element_key({'role': 'Button', 'name': '  Submit   Request! '}) == ('button', 'submit_request')


def test_verified_router_hands_over_on_disagreement():
    screen = ScreenAdapter()
    px = np.full((48, 64, 3), 238, np.uint8)
    a = {'pixels': px, 'title': 'Export', 'dom': FORM}
    b = {'pixels': px, 'title': 'Export', 'dom': LOOKALIKE}
    skills = SkillTable({'FORM3': ('SUBMIT', ['DONE']), 'DONE': ('DONE', None, True)})
    v = DomVerifier.fit([('FORM3', FORM)], targets={'SUBMIT': ('button', 'Submit request')})
    vr = VerifiedRouter(Router(Stub({screen(a): ('FORM3', 0.99)}), skills, adapter=screen), v)
    vr.reset(expect=['FORM3'])
    r = vr.route(b)
    assert r.kind == 'handoff' and r.reason == VERIFY_DISAGREE and r.detail == 'missing_elements' and r.state == 'FORM3'
    assert vr.counts == {'agree': 0, 'disagree': 1} and len(vr.router.take_handed_over()) == 1
    assert vr.router.check_progress('FORM3') is None  # expectation cleared, as after any hand-over
    vr.reset(expect=['FORM3'])
    ok = vr.route(a)
    assert ok.kind == 'action' and ok.action == 'SUBMIT' and vr.last_verdict.agree
    # a hand-over of the wrapped router passes through without a DOM check
    vr.reset(expect=['FORM3'])
    low = vr.route({'pixels': np.zeros((48, 64, 3), np.uint8), 'title': 'x', 'dom': FORM})
    assert low.reason == 'low_confidence' and vr.last_verdict is None
    assert refused(vr.route, {'pixels': px, 'title': 'Export'}) and refused(VerifiedRouter, object(), v)


def test_verifier_point_and_per_call_target():
    items = {'elements': [el('button', '치즈버거', x=52, y=130), el('button', '불고기버거', x=372, y=130)]}
    for e in items['elements']:
        e['w'], e['h'] = 280, 220
    v = DomVerifier({'ITEMS': []})
    assert v.verify('ITEMS', 'PICK_ITEM', items, target=('button', '불고기버거'), point=(512, 240)).agree
    moved = v.verify('ITEMS', 'PICK_ITEM', items, target=('button', '불고기버거'), point=(192, 240))
    assert not moved.agree and moved.reason == 'target_moved'  # the layout shifted: the fixed click would hit 치즈버거
    assert v.verify('ITEMS', 'PICK_ITEM', items, target=('button', '새우버거')).reason == 'no_target'
    items['elements'][1]['enabled'] = False
    assert v.verify('ITEMS', 'PICK_ITEM', items, target=('button', '불고기버거'), point=(512, 240)).reason == 'target_disabled'
    # VerifiedRouter passes the mission's target and click point through `where`
    screen = ScreenAdapter()
    px = np.full((48, 64, 3), 238, np.uint8)
    obs = {'pixels': px, 'title': 'Burger', 'dom': items}
    vr = VerifiedRouter(Router(Stub({screen(obs): ('ITEMS', 0.99)}), SkillTable({'ITEMS': ('PICK_ITEM', ['OPTION_1'])}),
                               adapter=screen), v, where=lambda route, o: {'target': ('button', '치즈버거'), 'point': (512, 240)})
    r = vr.route(obs)
    assert r.reason == VERIFY_DISAGREE and r.detail == 'target_moved'
    assert refused(VerifiedRouter, vr.router, v, where='not callable')


def popup(*controls, dialog=2, covered=False):
    return {'elements': [el('button', '주문하기', 600, 690, covered=True)] +
            [dict(el('button', n, 300 + 120 * i, 400, covered=covered), dialog=dialog) for i, n in enumerate(controls)]}


def test_popup_guard():
    g = PopupGuard()
    ok = g.check(popup('닫기'))
    assert ok.ok and ok.control['name'] == '닫기' and ok.point == (350.0, 420.0) and ok.ms >= 0
    assert g.check(popup('✕')).ok and g.check(popup('X')).ok and g.check(popup('자세히 보기', '닫기')).ok
    assert g.check(popup('오늘 하루 보지 않기', '닫기')).control['name'] == '닫기'  # prefers close
    nv = g.check(popup('다시 보지 않기'))
    assert not nv.ok and nv.reason == 'never_again_not_allowed'
    assert PopupGuard(allow_never_again=True).check(popup('다시 보지 않기')).ok
    # popups that ask for a decision are never dismissed automatically, even with a close control
    for controls in [('결제하기', '닫기'), ('연장하기', '닫기'), ('나가기', '닫기'), ('동의', '✕'), ('확인',)]:
        r = g.check(popup(*controls))
        assert not r.ok and r.reason == 'decision_needed' and r.control is None, controls
    assert g.check({'elements': [el('button', '닫기')]}).reason == 'no_dialog'
    assert g.check(popup('닫기', covered=True)).reason == 'no_dialog'
    assert g.check(popup('자세히 보기')).reason == 'no_dismiss_control'
    # two dialogs: only the topmost one counts
    two = popup('닫기', dialog=2)
    two['elements'].append(dict(el('button', '담기', 600, 560), dialog=1))
    assert g.check(two).ok
    assert 'dialog' in DomAdapter()(popup('닫기')) and 'dialog' not in DomAdapter()(FORM)


def test_exports():
    for name in ['DomAdapter', 'CombinedAdapter', 'DomVerifier', 'VerifiedRouter', 'PopupGuard', 'ScreenAdapter', 'Router',
                 'Decider']:
        assert name in simthinkd.__all__ and hasattr(simthinkd, name)


CASES = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]

if __name__ == '__main__':
    for f in CASES:
        f()
    print(f'dom adapter tests: {len(CASES)} passed')
