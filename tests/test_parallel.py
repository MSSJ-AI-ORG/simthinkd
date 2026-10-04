"""Parallel questions (Decider.ask) and batch inference (predict_batch, ask_batch): answers must not change."""
import copy
import json
from pathlib import Path

try:
    import pytest
except ImportError:  # CI runs this file as a script without pytest
    pytest = None

from simthinkd import Decider

STATES = Path(__file__).resolve().parent.parent / 'src' / 'simthinkd' / 'data' / 'doom_defend_states.json'
parametrize = pytest.mark.parametrize if pytest else (lambda *a, **k: (lambda f: f))
TOL = 1e-6  # float32 network: a padded batch may round differently in the last bits, never in the choice


def bodies(n=300):
    return [r['body'] for r in json.loads(STATES.read_text(encoding='utf8'))['rows'][:n]]


def assert_same(a, b):
    assert a.keys() == b.keys()
    for q in a:
        assert a[q]['choice'] == b[q]['choice']
        assert a[q]['probabilities'].keys() == b[q]['probabilities'].keys()
        for k, p in a[q]['probabilities'].items():
            assert abs(p - b[q]['probabilities'][k]) <= TOL


def with_question(body, name, question):
    body = copy.deepcopy(body)
    body['questions'][name] = question
    return body


DANGER = {'type': 'choice', 'instructions': {'goal': 'Which side is more dangerous?'},
          'criteria': {'left': 'More enemies on the left.', 'right': 'More enemies on the right.', 'none': 'No enemy close.'}}
URGENCY = {'type': 'score', 'instructions': {'goal': 'How urgent is the situation?'},
           'criteria': ['calm', 'some pressure', 'under attack', 'about to die']}
RELOAD = {'type': 'noul', 'instructions': {'goal': 'Should we save ammunition now?'}}


@parametrize('preset', ['doom-defend', 'doom-corridor'])
def test_predict_batch_equals_one_at_a_time(preset):
    d = Decider(preset)
    xs = bodies() if preset == 'doom-defend' else [d.request(s) for s in (
        'enemies: ShotgunGuy left near offset15 | goal: armor ahead distant | body healthy | ammo stocked',
        'enemies: none | goal: armor ahead near | body hurt | ammo low',
        'enemies: Zombieman right near offset5 ; ShotgunGuy left far offset30 | goal: armor ahead distant | body healthy | ammo stocked')]
    for single, batched in zip([d.predict(b) for b in xs], d.predict_batch(xs)):
        assert_same(single, batched)


def test_ask_on_a_plain_request_equals_predict():
    d = Decider('doom-defend')
    for body in bodies(100):
        assert_same(d.ask(body)['answers'], d.predict(body))


def test_extra_questions_do_not_change_the_operation_answer():
    d = Decider('doom-defend')
    for body in bodies(100):
        plain = d.predict(body)
        multi = d.ask(with_question(with_question(with_question(body, 'danger', DANGER), 'urgency', URGENCY), 'reload', RELOAD))
        assert_same({k: multi['answers'][k] for k in plain}, plain)
        assert multi['meta']['questions'] == 4


def test_questions_stay_independent_of_each_other():
    d = Decider('doom-defend')
    other = {'type': 'choice', 'instructions': {'goal': 'Pick a colour.'},
             'criteria': {f'c{i}': f'colour number {i}' for i in range(40)}}  # many rows: changes the padded shape
    for body in bodies(50):
        alone = d.ask(with_question(body, 'danger', DANGER))['answers']['danger']
        mixed = d.ask(with_question(with_question(body, 'danger', DANGER), 'colour', other))['answers']['danger']
        assert alone['choice'] == mixed['choice']
        assert all(abs(alone['probabilities'][k] - mixed['probabilities'][k]) <= TOL for k in alone['probabilities'])


def test_score_and_noul_answers_have_their_shape():
    d = Decider('doom-defend')
    a = d.ask(with_question(with_question(bodies(1)[0], 'urgency', URGENCY), 'reload', RELOAD))['answers']
    assert a['urgency']['type'] == 'score' and 1 <= a['urgency']['score'] <= 4
    assert abs(sum(a['urgency']['probabilities'].values()) - 1) <= TOL
    assert a['reload']['type'] == 'noul' and 0 <= a['reload']['noul'] <= 1
    assert set(a['reload']['probabilities']) == {'true', 'false'}


def test_ask_batch_equals_ask():
    d = Decider('doom-defend')
    xs = [with_question(b, 'danger', DANGER) if i % 2 else b for i, b in enumerate(bodies(60))]
    for one, many in zip([d.ask(b) for b in xs], d.ask_batch(xs)):
        assert one['meta'] == many['meta']
        assert_same({k: v for k, v in one['answers'].items() if 'choice' in v},
                    {k: v for k, v in many['answers'].items() if 'choice' in v})


def test_question_only_request_without_operation():
    d = Decider('doom-defend')
    body = {'state': bodies(1)[0]['state'], 'questions': {'danger': DANGER, 'reload': RELOAD}}
    a = d.ask(body)
    assert set(a['answers']) == {'danger', 'reload'} and a['meta']['questions'] == 2


@parametrize('bad', [{'type': 'score', 'criteria': ['only one']},
                                 {'type': 'noul', 'criteria': {'yes': 'a', 'no': 'b'}},
                                 {'type': 'rank', 'criteria': {'a': 'a'}},
                                 {'type': 'choice'}])
def test_bad_questions_are_refused(bad):
    try:
        Decider('doom-defend').ask(with_question(bodies(1)[0], 'bad', bad))
    except ValueError:
        return
    raise AssertionError(f'bad question accepted: {bad}')


def target_body(n, seed):
    """An operation request with an ATTACK target question of n enemies and a WAIT operation without targets."""
    enemies = {f'e{i}': {'element': f'[enemy] e{i}', 'description': f'Zergling dist {10 + 7 * ((i + seed) % 9)} hp {20 + 5 * i}'}
               for i in range(n)}
    return {'state': {'page': {'url': 'sim://custom', 'title': '', 'text': f'me: Marine | enemies {n}'}, 'elements': [], 'recent_actions': []},
            'questions': {'operation': {'type': 'choice', 'instructions': {'goal': 'Win the fight.'},
                                        'criteria': {'ATTACK': 'Attack one enemy.', 'WAIT': 'Hold position.'}},
                          'attack_target': {'type': 'choice', 'criteria': enemies}}}


def test_targets_with_unequal_counts_route_and_batch_correctly():
    d = Decider('doom-defend')
    xs = [target_body(n, s) for s in range(3) for n in (1, 2, 5, 9, 17)]
    singles = [d.predict(b) for b in xs]
    for single, batched, asked in zip(singles, d.predict_batch(xs), d.ask_batch(xs)):
        assert_same(single, batched)
        assert_same(single, asked['answers'])


def test_scores_batch_equals_scores_block_by_block():
    from simthinkd.policy import encode
    d = Decider('doom-defend')
    blocks = [encode(b)[0] for b in bodies(20)] + [encode(target_body(9, 1))[0]]
    blocks += [blocks[0][:1], blocks[-1][:3]]  # single-row and cut blocks, mixed sizes
    for block, s in zip(blocks, d.policy.scores_batch(blocks)):
        single = d.policy.scores(block)
        assert s.dtype == single.dtype and s.shape == single.shape
        # raw scores are float32 logits: compare relative to their size (probabilities are checked at 1e-6 elsewhere)
        assert all(abs(float(a) - float(b)) <= 1e-5 * max(1.0, abs(float(b))) for a, b in zip(s, single))


def test_empty_inputs():
    d = Decider('doom-defend')
    assert d.predict_batch([]) == [] and d.ask_batch([]) == [] and d.policy.scores_batch([]) == []
    assert len(d.ask_batch(iter(bodies(2)))) == 2  # any iterable, read once
    from simthinkd.policy import encode
    x = encode(bodies(1)[0])[0]
    for blocks in ([x, x[:0]], [x[:0], x]):
        try:
            d.policy.scores_batch(blocks)
        except ValueError:
            continue
        raise AssertionError('an empty block was accepted')


def test_score_and_noul_values_match_their_probabilities_in_batches():
    d = Decider('doom-defend')
    xs = [with_question(with_question(b, 'urgency', URGENCY), 'reload', RELOAD) for b in bodies(40)]
    for one, many in zip([d.ask(b) for b in xs], d.ask_batch(xs)):
        for a in (one['answers'], many['answers']):
            u, r = a['urgency'], a['reload']
            assert u['score'] == int(max(u['probabilities'], key=u['probabilities'].get))
            assert r['noul'] == r['probabilities']['true']
        assert one['answers']['urgency']['score'] == many['answers']['urgency']['score']
        assert abs(one['answers']['reload']['noul'] - many['answers']['reload']['noul']) <= TOL


if __name__ == '__main__':  # CI runs test files as scripts
    cases = [(test_predict_batch_equals_one_at_a_time, p) for p in ('doom-defend', 'doom-corridor')]
    cases += [(f, None) for f in (test_ask_on_a_plain_request_equals_predict, test_extra_questions_do_not_change_the_operation_answer,
                                  test_questions_stay_independent_of_each_other, test_score_and_noul_answers_have_their_shape,
                                  test_ask_batch_equals_ask, test_question_only_request_without_operation,
                                  test_targets_with_unequal_counts_route_and_batch_correctly, test_scores_batch_equals_scores_block_by_block,
                                  test_empty_inputs, test_score_and_noul_values_match_their_probabilities_in_batches)]
    for f, arg in cases:
        f(arg) if arg else f()
    for bad in [{'type': 'score', 'criteria': ['only one']}, {'type': 'noul', 'criteria': {'yes': 'a', 'no': 'b'}},
                {'type': 'rank', 'criteria': {'a': 'a'}}, {'type': 'choice'}]:
        test_bad_questions_are_refused(bad)
    print(f'parallel tests: {len(cases) + 4} passed')
