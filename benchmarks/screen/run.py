"""Local, synthetic screen benchmark. No external model is called by default."""
import argparse
import contextlib
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def mission(app, seed):
    """Port of the ERP app's seeded target generator; no browser needed."""
    if app == 'img':
        return dict(prompt='a lighthouse on a rocky coast at sunset', style='Watercolor',
                    ratio='16:9', count=4, download=2)
    a = seed * 7919 + 13

    def rand():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xffffffff
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xffffffff
        t = (t ^ ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xffffffff)) & 0xffffffff)) & 0xffffffff
        return ((t ^ (t >> 14)) & 0xffffffff) / 4294967296

    def pick(seq):
        return seq[int(rand() * len(seq))]

    employees = []
    names = set()
    while len(employees) < 14:
        name = pick('김이박최정강조윤장임한오서신권황안송류홍') + pick(
            ['민준','서연','도윤','하은','시우','지유','주원','수아','예준','지아','건우','서윤','현우','채원','우진','지민','유나','태윤'])
        if name in names:
            continue
        names.add(name)
        for _ in range(8):
            rand()  # employee number, dept, rank, date(3), extension, site
        wfh = int(rand() * 4)
        rand()  # leave balance
        employees.append((name, wfh))
    target = employees[2 + int(rand() * 10)]
    to = min(5, target[1] + 1 + int(rand() * 2))
    request = [e for e in employees if e != target][int(rand() * 13)][0]
    return dict(employee=target[0], w0=target[1], w1=to, request=request)


def build_summary(rows):
    ordered = sorted(rows, key=lambda r: (r['app'], r['cond'], r['seed'], r['rep']))
    groups = {}
    for r in ordered:
        key = r['app'] + '/' + r['cond']
        groups.setdefault(key, []).append(r)
    return {'schema': 'screen-bench/1', 'runs': ordered, 'groups': {
        key: {'runs': len(rs), 'successes': sum(bool(r['success']) for r in rs),
              'mean_seconds': sum(r['total_seconds'] for r in rs) / len(rs),
              'llm_calls': sum(r['llm_calls'] for r in rs)} for key, rs in sorted(groups.items())}}


def find_chrome(explicit=None):
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p)
        raise FileNotFoundError('--chrome must name an existing executable')
    candidates = [shutil.which(n) for n in ('google-chrome','chromium','chromium-browser','chrome')]
    candidates += [str(Path(os.environ.get(k, '')) / 'Google/Chrome/Application/chrome.exe')
                   for k in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA')]
    candidates += ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                   '/Applications/Chromium.app/Contents/MacOS/Chromium']
    for p in candidates:
        if p and Path(p).is_file():
            return p
    raise FileNotFoundError('Chrome not found; use --chrome PATH')


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def browser(chrome, output):
    import cdp
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(HERE / 'apps')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix='chrome-', dir=output) as profile:
            with (output / 'chrome.log').open('wb') as log:
                process = subprocess.Popen([chrome, '--headless=new', '--remote-debugging-address=127.0.0.1',
                    '--remote-debugging-port=0', '--user-data-dir=' + profile, '--no-first-run',
                    '--no-default-browser-check', '--disable-background-networking', '--disable-extensions',
                    '--window-size=1280,768', 'about:blank'], stdout=log, stderr=log)
                try:
                    active = Path(profile) / 'DevToolsActivePort'
                    deadline = time.monotonic() + 30
                    while not active.exists():
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError('Chrome failed to start; inspect chrome.log')
                        time.sleep(.1)
                    cdp.CDP = 'http://127.0.0.1:' + active.read_text().splitlines()[0]
                    yield 'http://127.0.0.1:' + str(server.server_port)
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def model_adapter(command):
    """JSON on stdin, one JSON action on stdout; argv array preferred on Windows."""
    argv = json.loads(command) if command.lstrip().startswith('[') else shlex.split(command)
    if not isinstance(argv, list) or not argv or not all(isinstance(s, str) for s in argv):
        raise ValueError('--llm-cmd must be a command or JSON string array')

    def call(png, app, params, previous, log_dir):
        import engine
        shot = Path(log_dir) / ('shot_' + hashlib.sha256(png).hexdigest()[:16] + '.png')
        shot.write_bytes(png)
        payload = dict(schema='screen-bench-action/1', screenshot=str(shot.resolve()),
                       mission=engine.instr(app, params), previous=previous[-14:],
                       actions=['PRESS label [#N]', 'TYPE label := text', 'WAIT', 'DONE'])
        start = time.perf_counter()
        r = subprocess.run(argv, input=json.dumps(payload), text=True, encoding='utf-8',
                           capture_output=True, timeout=180, check=True, shell=False)
        answer = json.loads(r.stdout)
        action = answer.get('action')
        if action in ('WAIT','DONE'):
            parsed = (action,)
        elif action == 'PRESS' and isinstance(answer.get('label'), str):
            parsed = (action, answer['label'])
        elif action == 'TYPE' and all(isinstance(answer.get(k), str) for k in ('label','text')):
            parsed = (action, answer['label'], answer['text'])
        else:
            raise ValueError('Invalid LLM action JSON')
        return parsed, (time.perf_counter()-start)*1000, {'error': None}
    return call


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', choices=['erp','img'], required=True)
    parser.add_argument('--cond', choices=['decider','llm'], required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--reps', type=int, default=1)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--chrome')
    parser.add_argument('--llm-cmd')
    parser.add_argument('--train-seeds', type=int, default=60, help='Pilot override; default reproduces 60 teacher seeds')
    args = parser.parse_args(argv)
    if args.reps < 1 or args.train_seeds < 1 or not 1 <= args.seed <= 2147483647:
        parser.error('reps/train-seeds must be positive; seed must be 1..2147483647')
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.glob('timings/*_rep*.json')) or (args.out / 'SUMMARY.json').exists():
        parser.error('Use a fresh --out directory to preserve previous runs')
    if args.cond == 'llm' and not args.llm_cmd:
        result = {'schema':'screen-bench/1', 'status':'skipped', 'reason':'--llm-cmd is required for llm', 'runs':[]}
        (args.out / 'SUMMARY.json').write_text(canonical(result), encoding='utf-8')
        print('SKIPPED: --llm-cmd is required for llm')
        return 0
    if 1001 <= args.seed < 1001 + args.train_seeds:
        parser.error('Mission seed overlaps teacher seeds')
    import engine
    engine.OUT = args.out.resolve()
    engine.TRAIN_SEEDS = range(1001,1001+args.train_seeds)
    engine.big_model = model_adapter(args.llm_cmd) if args.llm_cmd else None
    engine.mission_params = lambda app: (mission(app, args.seed), args.seed, 'notice' if app == 'erp' else 'credits')
    for name in ('data','models','raw','timings'):
        (engine.OUT / name).mkdir(exist_ok=True)
    rows = []
    with browser(find_chrome(args.chrome), engine.OUT) as base:
        engine.BASE = base
        # Check the independent mission generator against the app before training.
        tab = engine.Tab()
        try:
            engine.open_app(tab, args.app, args.seed, 'none')
            if args.app == 'erp' and engine.erp_params(engine.oracle(tab)) != mission('erp', args.seed):
                raise RuntimeError('Mission generator disagrees with synthetic app')
        finally:
            tab.close()
        if args.cond == 'decider':
            engine.collect(args.app)
            engine.train(args.app)
        brain = engine.Brain(args.app) if args.cond == 'decider' else None
        for rep in range(1,args.reps+1):
            row = engine.run(args.app, 'verify' if args.cond == 'decider' else 'llm', rep, brain=brain)
            row['cond'] = args.cond
            row['training_included_in_total'] = False
            row['status'] = 'passed' if row['success'] else 'failed'
            (engine.OUT / 'timings' / f'{args.app}_{args.cond}_rep{rep}.json').write_text(canonical(row), encoding='utf-8')
            rows.append(row)
    (args.out / 'SUMMARY.json').write_text(canonical(build_summary(rows)), encoding='utf-8')
    return 0 if all(r['success'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
