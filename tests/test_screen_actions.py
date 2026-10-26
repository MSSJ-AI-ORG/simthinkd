"""Screen actions: each guard blocks the case it exists for, and a planted wrong case is caught."""
import pytest

from simthinkd import ExpectAfter, NoClickBands, PageTextCheck, RuleFirst, open_or_press


def test_bands_block_header_and_footer_only():
    b = NoClickBands(top=345, bottom_from=940)
    assert not b.allows((640, 100)) and not b.allows((640, 960)) and b.allows((640, 500))
    assert b.visible_part({'x': 0, 'y': 300, 'w': 100, 'h': 100}) == (50.0, 372.5)  # only the part below the header
    assert b.visible_part({'x': 0, 'y': 0, 'w': 100, 'h': 300}) is None             # wholly under the header
    with pytest.raises(ValueError):
        NoClickBands(top=-1)


def test_open_link_by_address_else_press():
    assert open_or_press({'role': 'link', 'href': 'https://example.org/p/1', 'x': 0, 'y': 0, 'w': 10, 'h': 10}) == ('open', 'https://example.org/p/1')
    assert open_or_press({'role': 'link', 'href': 'javascript:void(0)', 'x': 0, 'y': 0, 'w': 10, 'h': 20}) == ('press', (5.0, 10.0))
    other = lambda href: href.startswith('https://example.org/')
    assert open_or_press({'href': 'https://elsewhere.test/x', 'x': 2, 'y': 2, 'w': 2, 'h': 2}, allow=other)[0] == 'press'


def test_expect_after_hits_and_times_out():
    t = [0.0]
    states = iter([None, 'LOADING', 'PRODUCT'])
    ea = ExpectAfter(lambda: next(states), timeout=5, poll=1, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
    ok, state, ms = ea.wait({'PRODUCT'})
    assert ok and state == 'PRODUCT' and ms == 2000.0
    t[0] = 0.0
    ea2 = ExpectAfter(lambda: 'LIST', timeout=3, poll=1, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
    ok, state, _ = ea2.wait({'PRODUCT'})
    assert not ok and state == 'LIST'                                    # planted wrong screen: never accepted


def test_rule_first_then_fallback_and_broken_rule():
    calls = []
    fb = lambda obs: calls.append(obs) or type('R', (), {'kind': 'action', 'action': 'DECIDED'})()
    def broken(obs):
        raise RuntimeError('rule bug')
    rf = RuleFirst([(broken, 'NEVER'), (lambda o: 'cart' in o, 'ADD')], fallback=fb)
    assert rf.route('a cart button').kind == 'rule' and rf.route('a cart button').action == 'ADD' and not calls
    r = rf.route('search page')
    assert r.kind == 'action' and r.action == 'DECIDED' and calls == ['search page']


def test_page_text_words_and_counter():
    c = PageTextCheck(words=['Added to cart'], count=lambda t: int(t.split('cart:')[1]) if 'cart:' in t else None)
    c.begin('cart:1')
    assert c.done('... ADDED   to cart ...') and c.done('cart:2')
    assert not c.done('cart:1')                                         # planted: same count is not success
    with pytest.raises(ValueError):
        PageTextCheck()
