"""Router kit example end to end, twice: the sealed PREREG still matches its code, the run is reproducible, and the
recorded hypotheses still hold.

    python -X utf8 tests/test_router_example.py        (needs simthinkd[train]; about a minute on a CPU)

Exit 0 = all pass. This runs examples/router_screen/run.py exactly as its README says, into two temporary folders.
The digest covers every count and choice (not times), so two runs on one machine must agree. It is not compared with
the digest in RESULTS_router_screen_v1.json: training on another CPU or PyTorch build may round differently.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'router_screen'
PY = sys.executable


def run(out):
    r = subprocess.run([PY, '-X', 'utf8', str(EXAMPLE / 'run.py'), '--out', str(out), '--quiet'], capture_output=True, text=True,
                       cwd=EXAMPLE)
    ok = r.returncode == 0 and (out / 'result.json').exists()
    return (json.loads((out / 'result.json').read_text(encoding='utf8')) if ok else None), (r.stdout + r.stderr)[-600:]


def main():
    results = []
    sys.path.insert(0, str(EXAMPLE))
    import seal_prereg
    problems = seal_prereg.verify(EXAMPLE / 'PREREG_router_screen.json')
    results.append(('PREREG sealed and frozen code unchanged', not problems, problems))
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        first, log1 = run(t / 'a')
        second, log2 = run(t / 'b')
        results.append(('example runs', first is not None and second is not None, log1 + log2))
        if first and second:
            results.append(('same digest twice (reproducible)', first['digest'] == second['digest'], (first['digest'], second['digest'])))
            r = first
            clean = r['learned_by_perturb']['none']
            unseen = [r['learned_by_perturb'][p] for p in ('banner', 'session')]
            results += [
                ('H1 clean runs all succeed, hand-over rate <= 0.20', clean['success'] == clean['trials'] and clean['handoff_rate'] <= 0.2, clean),
                ('H2 unseen screens >= 90% success, no false stop',
                 sum(u['success'] for u in unseen) >= 0.9 * sum(u['trials'] for u in unseen) and r['learned']['false_stop'] == 0, unseen),
                ('H3 every wrong fast action caught at the next route',
                 all(r[k]['fast_wrong_not_caught'] == 0 for k in ('learned', 'negative_wrong_expectation', 'negative_wrong_action')), None),
                ('H4 wrong expectation and wrong action are caught by no-progress',
                 r['negative_wrong_expectation']['handoff_reasons'].get('no_progress', 0) >= r['negative_wrong_expectation']['trials']
                 and r['negative_wrong_action']['fast_wrong'] >= r['negative_wrong_action']['trials']
                 and r['negative_wrong_action']['fast_wrong_caught_by_no_progress'] == r['negative_wrong_action']['fast_wrong'], None),
                ('H5 trigger fires on the redesign', r['trigger']['fired_at'] is not None, r['trigger']),
                ('H6 after relearning: all succeed, hand-over rate <= learned + 0.10',
                 r['redesign_after']['success'] == r['redesign_after']['trials']
                 and r['redesign_after']['handoff_rate'] <= clean['handoff_rate'] + 0.10, r['redesign_after']),
                ('H7 layout A after relearning: all succeed', r['layout_A_after']['success'] == r['layout_A_after']['trials'], None),
                ('relearn hot-swapped the decider and logged one line',
                 r['relearn']['swapped'] and len((t / 'a' / 'relearn.jsonl').read_text(encoding='utf8').splitlines()) == 1, r['relearn']),
            ]
    for name, ok, info in results:
        print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f' | {info}'))
    return 0 if results and all(ok for _, ok, _ in results) else 1


if __name__ == '__main__':
    sys.exit(main())
