"""Package self-test: API, CLI, HTTP server, benchmark, training, integrations. Exit 0 = all pass.

    python -X utf8 tests/test_package.py [--no-train]
"""
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import simthinkd
from simthinkd import Decider, bench, toy
from simthinkd.core import PRESETS, WEIGHTS

EXAMPLE = 'seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25'
checks = []


def check(name, ok):
    checks.append((name, bool(ok)))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def post(port, body):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/v1/systemone', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def main():
    d = Decider('doom-defend')
    r = d.decide(EXAMPLE)
    check('decide returns an offered action', r.choice in d.actions)
    check('probabilities sum to 1', abs(sum(r.probabilities.values()) - 1) < 1e-6)
    check('enemy on the left -> TURN_LEFT', r.choice == 'TURN_LEFT')
    sums = {line.split()[1].lstrip('*'): line.split()[0] for line in (WEIGHTS / 'SHA256SUMS').read_text().splitlines()}
    check('bundled weights match SHA256SUMS', all(sums[p['weights']] == p['sha256'] for p in PRESETS.values()))
    try:
        Decider('doom-defend').decide('')
        check('empty state rejected', False)
    except ValueError:
        check('empty state rejected', True)

    result = bench.run(limit=300)
    check(f'bench: teacher agreement {result["teacher_agreement"]} >= 0.9', result['teacher_agreement'] >= 0.9)
    check(f'bench: within one tick {result["within_one_tick"]} >= 0.99', result['within_one_tick'] >= 0.99)

    out = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'simthinkd.cli', 'decide', '--json'], capture_output=True, text=True)
    check('cli decide --json', out.returncode == 0 and json.loads(out.stdout)['choice'] == 'TURN_LEFT')

    from simthinkd.server import ThreadingHTTPServer, make_handler
    port = free_port()
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(d, 'test', 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        reply = post(port, d.request(EXAMPLE))
        check('server answer equals in-process answer', reply['answers']['operation']['choice'] == r.choice)
        check('server reports weights sha', reply['meta']['weights_sha256'] == d.sha256)
        try:
            post(port, {'state': {}})
            check('server rejects malformed request with 400', False)
        except urllib.error.HTTPError as e:
            check('server rejects malformed request with 400', e.code == 400)
    finally:
        server.shutdown()

    try:
        from simthinkd.integrations.langchain_tool import simthinkd_tool
        check('langchain tool', simthinkd_tool().invoke({'state': EXAMPLE})['choice'] == 'TURN_LEFT')
    except ImportError:
        print('SKIP langchain (not installed)')
    try:
        import asyncio
        from simthinkd.integrations import mcp_server
        names = [t.name for t in asyncio.run(mcp_server.build_server().list_tools())]
        check('mcp server exposes decide + list_deciders', {'decide', 'list_deciders'} <= set(names))
    except ImportError:
        print('SKIP mcp (not installed)')

    if '--no-train' not in sys.argv:
        import random
        with tempfile.TemporaryDirectory() as tmp:
            start = time.perf_counter()
            mine = simthinkd.fit(toy.examples(3000), toy.ACTIONS, goal=toy.GOAL, out=Path(tmp) / 'inspection', quiet=True)
            seconds = time.perf_counter() - start
            rng = random.Random(12345)
            fresh = [toy.observe(rng) for _ in range(500)]
            agree = sum(mine.decide(text).choice == toy.teacher(s) for s, text in fresh) / len(fresh)
            check(f'fit: toy agreement on 500 fresh states {agree:.3f} >= 0.95 ({seconds:.1f} s)', agree >= 0.95)
            again = Decider(str(Path(tmp) / 'inspection'))
            check('trained decider reloads from its folder', again.sha256 == mine.sha256)

    for name, ok in checks:
        print(('PASS ' if ok else 'FAIL ') + name)
    sys.exit(0 if all(ok for _, ok in checks) else 1)


if __name__ == '__main__':
    main()
