"""Router kit example: the screen-router logic of experiments v2.1 and v2.2 on a small synthetic screen task.

    pip install "simthinkd[train]"
    python run.py --out out            # about a minute on a CPU; writes out/result.json and out/relearn.jsonl

No browser, no network, no large-model calls. The "large model" is a stub that reads the app's true state and applies
the task's rules (screens.POLICY); it is counted like a model call. Phases (seeds and settings: PREREG_router_screen.json):

  1 teach    stub teacher runs the task on layout A (clean screens with small local variation) -> (sentence, state) examples
             and (state, action, next state) transitions -> SkillTable.from_transitions (expected next states)
  2 train    simthinkd.fit on those examples (600 steps, seed 31, CPU)
  3 learned  router + stub large model on layout A; 40% of runs meet a screen never trained on (banner or session page)
  4 wrong    negative controls: the same runs with a deliberately wrong skill table (a wrong expected state; a wrong action)
             -> every wrong fast action must be caught by a no-progress hand-over at the very next observation
  5 redesign the learned router meets layout B with the sealed v2.2 trigger (10 routes, hand-over rate 0.5, 3 no-progress)
  6 relearn  stub teacher labels the handed-over screens and 12 teacher runs on B; retrain; hot-swap; log
  7 after    the relearned router on fresh layout-B runs, and on layout A again (it should not forget)

`digest` in result.json covers every count and choice (not times); two runs on the same machine give the same digest.
"""
import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'src'))  # run from a clone without installing

import simthinkd  # noqa: E402
from simthinkd import HandoffMonitor, Router, ScreenAdapter, Skill, SkillTable, relearn  # noqa: E402

import screens  # noqa: E402

PREREG = HERE / 'PREREG_router_screen.json'
GOAL = 'Recognise which screen of the fixed task is showing.'
DESCRIPTIONS = {'LOGIN': 'Sign-in form', 'PROFILE': 'Profile form with a save button', 'ERROR': 'Error dialog over the form',
                'DONE': 'Saved page'}


def big_model(observation):
    """Stub for the large model on the slow path: the right action for the true screen (no network)."""
    return screens.POLICY[observation['truth']]


def teacher_label(observation):
    """Stub teacher for relearning: the true screen state, or None for screens outside the task (skipped)."""
    return observation['truth'] if observation['truth'] in screens.STATES else None


def teacher_run(layout, seed, examples, transitions, adapter, observations=None):
    app, prev = screens.App(layout, seed), None
    for _ in range(10):
        obs = app.observe(prev)
        examples.append((adapter(obs), obs['truth']))
        if observations is not None:
            observations.append(obs)
        action = screens.POLICY[obs['truth']]
        if action == 'STOP':
            transitions.append((obs['truth'], action, None))
            return app.success
        app.do(action)
        transitions.append((obs['truth'], action, app.truth))
        prev = action
    return False


def trial(app, router, max_actions):
    router.reset(expect=screens.START)
    prev, steps = None, []
    while len(steps) < max_actions:
        obs = app.observe(prev)
        route = router.route(obs)
        if route.kind == 'action':
            action = route.action
            steps.append({'truth': obs['truth'], 'state': route.state, 'action': action, 'by': 'fast',
                          'wrong': route.state != obs['truth'] or action != screens.POLICY[obs['truth']], 'ms': route.ms})
        else:
            action = big_model(obs)
            steps.append({'truth': obs['truth'], 'state': route.state, 'action': action, 'by': 'big', 'reason': route.reason,
                          'detail': route.detail, 'ms': route.ms})
        if action == 'STOP':
            break
        app.do(action)
        prev = action
    claimed = bool(steps) and steps[-1]['action'] == 'STOP'
    ok = bool(app.success and claimed)
    return {'success': ok, 'false_stop': claimed and not ok, 'steps': steps}


def run_set(router, rows, max_actions):
    return [dict(trial(screens.App(layout, seed, perturb), router, max_actions), layout=layout, seed=seed, perturb=perturb)
            for layout, seed, perturb in rows]


def summary(trials):
    steps = [s for t in trials for s in t['steps']]
    fast = [s for s in steps if s['by'] == 'fast']
    wrong = [i for i, s in enumerate(steps) if s['by'] == 'fast' and s['wrong']]
    # a wrong fast action is caught when the next route of the same trial is a hand-over; a wrong final action (STOP)
    # cannot be caught by a later route and shows up as a false stop
    caught, by_no_progress, missed, final = 0, 0, 0, 0
    for t in trials:
        for i, s in enumerate(t['steps']):
            if s['by'] != 'fast' or not s['wrong']:
                continue
            if s['action'] == 'STOP':
                final += 1
                continue
            nxt = t['steps'][i + 1] if i + 1 < len(t['steps']) else None
            if nxt is not None and nxt['by'] == 'big':
                caught += 1
                by_no_progress += nxt['reason'] == 'no_progress'
            else:
                missed += 1
    ms = sorted(s['ms'] for s in steps)
    return {'trials': len(trials), 'success': sum(t['success'] for t in trials), 'false_stop': sum(t['false_stop'] for t in trials),
            'routes': len(steps), 'fast': len(fast), 'big_model_calls': len(steps) - len(fast),
            'big_calls_per_trial': round((len(steps) - len(fast)) / max(len(trials), 1), 3),
            'handoff_rate': round((len(steps) - len(fast)) / max(len(steps), 1), 4),
            'handoff_reasons': dict(sorted(Counter(s['reason'] for s in steps if s['by'] == 'big').items())),
            'fast_wrong': len(wrong), 'fast_wrong_caught_next': caught, 'fast_wrong_caught_by_no_progress': by_no_progress,
            'fast_wrong_not_caught': missed, 'fast_wrong_final': final,
            'route_ms_p50': round(statistics.median(ms), 3) if ms else None,
            'route_ms_p95': round(ms[int(0.95 * (len(ms) - 1))], 3) if ms else None}


def seeds(spec):
    lo, hi = spec
    return range(lo, hi + 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default='out', help='folder for models, result.json and relearn.jsonl')
    ap.add_argument('--prereg', default=str(PREREG))
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    pre = json.loads(Path(a.prereg).read_text(encoding='utf8'))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    say = (lambda *x: None) if a.quiet else (lambda *x: print(*x, flush=True))
    adapter = ScreenAdapter()
    tau, max_actions, schedule = pre['tau'], pre['max_actions'], pre['perturb_schedule']
    result = {'prereg': Path(a.prereg).name, 'prereg_sha256': hashlib.sha256(Path(a.prereg).read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
              'simthinkd': simthinkd.__version__}
    timing = {}

    # 1 teach on layout A
    examples, transitions = [], []
    ok = [teacher_run('A', s, examples, transitions, adapter) for s in seeds(pre['train_seeds'])]
    skills = SkillTable.from_transitions(transitions)
    skills.save(out / 'skills_A.json')
    result['teach'] = {'runs': len(ok), 'runs_ok': sum(ok), 'examples': len(examples), 'skills': skills.to_dict()}
    say('teach', result['teach']['examples'], 'examples;', skills)

    # 2 train
    t0 = time.perf_counter()
    decider = simthinkd.fit(examples, DESCRIPTIONS, goal=GOAL, out=str(out / 'router_A'), steps=pre['steps'], seed=pre['seed'], quiet=True)
    timing['train_A_seconds'] = round(time.perf_counter() - t0, 2)
    result['router_A_sha256'] = decider.sha256

    # 3 learned state, with unseen disturbances
    rows = [('A', s, schedule[i % len(schedule)]) for i, s in enumerate(seeds(pre['test_seeds']))]
    router = Router(decider, skills, tau=tau, adapter=adapter)
    learned = run_set(router, rows, max_actions)
    result['learned'] = summary(learned)
    result['learned_by_perturb'] = {p: summary([t for t in learned if t['perturb'] == p]) for p in sorted(set(schedule))}
    say('learned', result['learned'])

    # 4 negative controls: deliberately wrong skill tables must be caught at the next observation
    wrong_expect = SkillTable(skills.to_dict())
    wrong_expect.add('PROFILE', Skill('SUBMIT', ['LOGIN']))  # wrong expectation: SUBMIT never leads back to LOGIN
    wrong_action = SkillTable(skills.to_dict())
    wrong_action.add('LOGIN', Skill('SUBMIT', ['PROFILE']))  # wrong action: SUBMIT does nothing on the sign-in form
    clean = [r for r in rows if r[2] == 'none']
    result['negative_wrong_expectation'] = summary(run_set(Router(decider, wrong_expect, tau=tau, adapter=adapter), clean, max_actions))
    result['negative_wrong_action'] = summary(run_set(Router(decider, wrong_action, tau=tau, adapter=adapter), clean, max_actions))
    say('wrong expectation', result['negative_wrong_expectation'])
    say('wrong action', result['negative_wrong_action'])

    # 5 redesign: the learned router meets layout B, the sealed trigger watches
    monitor = HandoffMonitor(**pre['trigger'])
    router = Router(decider, skills, tau=tau, adapter=adapter, monitor=monitor)
    detect = run_set(router, [('B', s, 'none') for s in seeds(pre['detect_seeds'])], max_actions)
    result['redesign_before'] = summary(detect)
    result['trigger'] = monitor.state()
    say('redesign before relearning', result['redesign_before'], 'trigger', result['trigger'])

    # 6 relearn: teacher labels the handed-over screens + teacher runs on B; retrain; hot-swap; log
    handed = router.take_handed_over()
    teach_obs, ex_b, tr_b = [], [], []
    for s in seeds(pre['teach_seeds']):
        teacher_run('B', s, ex_b, tr_b, adapter, teach_obs)
    log = out / 'relearn.jsonl'
    log.unlink(missing_ok=True)
    report = relearn(router, teacher_label, handed + teach_obs, base_examples=examples, out=out / 'router_B',
                     steps=pre['steps'], seed=pre['seed'], log=log, force=not monitor.fired)
    timing['relearn_train_seconds'] = report.train_seconds
    result['relearn'] = {'forced': report.trigger['forced'], 'teacher_calls': report.teacher_calls,
                         'teacher_skipped': report.teacher_skipped, 'handed_over_screens': len(handed),
                         'new_examples': report.new_examples, 'examples': report.examples, 'labels': list(report.labels),
                         'old_sha256': report.old_sha256, 'new_sha256': report.new_sha256,
                         'swapped': router.decider.sha256 == report.new_sha256 != report.old_sha256}
    say('relearn', result['relearn'], f'{report.train_seconds:.1f} s training')

    # 7 after relearning: fresh B runs, and A again
    result['redesign_after'] = summary(run_set(router, [('B', s, 'none') for s in seeds(pre['after_seeds'])], max_actions))
    result['layout_A_after'] = summary(run_set(router, [('A', s, 'none') for s in seeds(pre['recheck_seeds'])], max_actions))
    say('redesign after relearning', result['redesign_after'])
    say('layout A after relearning', result['layout_A_after'])

    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if not k.endswith(('_ms_p50', '_ms_p95', 'seconds'))}
        return v
    result['digest'] = hashlib.sha256(json.dumps(strip(result), sort_keys=True).encode()).hexdigest()
    result['timing'] = timing
    (out / 'result.json').write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf8')
    say('digest', result['digest'])
    return result


if __name__ == '__main__':
    main()
