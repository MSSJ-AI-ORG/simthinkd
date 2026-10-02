"""Browser port parity: the JavaScript decider (web/simthinkd.js) must choose exactly what the Python decider chooses.

    python -X utf8 tests/test_web_parity.py            (needs node; run tools/export_web_weights.py first)
Cases: all 1,050 recorded Doom states + synthetic requests (Korean, punctuation, emoji, recent actions, extra fields,
the corridor decider, random sentences). Exit 0 only if 100% of choices agree; also reports the largest
probability difference (float32 vs float64 arithmetic).
"""
import json
import random
import subprocess
import sys
from pathlib import Path

from simthinkd import Decider

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests' / '.parity-data'


def synthetic(rng):
    defend, corridor = Decider('doom-defend'), Decider('doom-corridor')
    words = ['Demon', 'MarineChainsawVzd', 'left', 'right', 'ahead', 'a30', 'd5', '\uc801', '\uc67c\ucabd', 'ammo25', '!!', '...',
             'gun ready', 'gun wait', 'sway left', '🙂', 'Ｆｕｌｌｗｉｄｔｈ', 'naïve', 'x_y_z', '|', 'enemies 3', '①']
    cases = []
    for i in range(300):
        d = defend if i % 3 else corridor
        sentence = ' '.join(rng.choice(words) for _ in range(rng.randint(1, 12)))
        body = d.request(sentence, tick=rng.randint(0, 2000))
        if i % 5 == 0:
            body['state']['recent_actions'] = [{'action': rng.choice(list(d.actions)), 'page_changed': rng.random() < .5}
                                               for _ in range(rng.randint(1, 4))]
        if i % 7 == 0:
            body['state']['elements'].append({'id': 'EXTRA', 'role': 'link', 'label': '\ucd94\uac00 \uc694\uc18c', 'index': i})
        cases.append({'preset': 'doom-defend' if d is defend else 'doom-corridor', 'body': body})
    return cases


def main():
    states = json.loads((ROOT / 'src/simthinkd/data/doom_defend_states.json').read_text(encoding='utf8'))['rows']
    cases = [{'preset': 'doom-defend', 'body': r['body']} for r in states] + synthetic(random.Random(7))
    deciders = {name: Decider(name) for name in ['doom-defend', 'doom-corridor']}
    for c in cases:
        op = deciders[c['preset']].predict(c['body'])['operation']
        c['python'] = {'choice': op['choice'], 'probabilities': op['probabilities']}
    OUT.mkdir(exist_ok=True)
    path = OUT / 'cases.json'
    path.write_text(json.dumps(cases, ensure_ascii=False), encoding='utf8')
    run = subprocess.run(['node', str(ROOT / 'tests' / 'test_web_parity.mjs'), str(path)], capture_output=True, text=True,
                         encoding='utf8')
    print(run.stdout.strip() or run.stderr.strip())
    sys.exit(run.returncode)


if __name__ == '__main__':
    main()
