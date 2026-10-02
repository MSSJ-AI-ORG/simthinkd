"""simthinkd command line: decide · serve · bench · train · list."""
import argparse
import json
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog='simthinkd', description='SimThink D: a 2 ms decision model for real-time loops.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('decide', help='one decision for one situation sentence')
    s.add_argument('state', nargs='?', help='situation sentence (default: the preset example)')
    s.add_argument('--decider', default='doom-defend')
    s.add_argument('--json', action='store_true')
    s = sub.add_parser('serve', help='HTTP server (POST /v1/systemone)')
    s.add_argument('decider', nargs='?', default='doom-defend')
    s.add_argument('--host', default='127.0.0.1')
    s.add_argument('--port', type=int, default=11890)
    s.add_argument('--delay-ms', type=float, default=0.0)
    s = sub.add_parser('bench', help='decision time and teacher agreement on recorded states')
    s.add_argument('--url')
    s.add_argument('--name')
    s.add_argument('--decider', default='doom-defend')
    s.add_argument('--states')
    s.add_argument('--tick-hz', type=float, default=35.0)
    s.add_argument('--limit', type=int, default=0)
    s.add_argument('--json', action='store_true')
    s = sub.add_parser('train', help='train from a folder of protocol rows (needs simthinkd[train])')
    s.add_argument('--data', required=True)
    s.add_argument('--out', required=True)
    s.add_argument('--steps', type=int, default=600)
    s.add_argument('--seed', type=int, default=31)
    sub.add_parser('list', help='bundled deciders')
    a = ap.parse_args(argv)

    if a.cmd == 'decide':
        from .core import Decider
        d = Decider(a.decider)
        state = a.state or d.preset.get('example')
        if not state:
            sys.exit('give a situation sentence')
        r = d.decide(state)
        print(json.dumps({'choice': r.choice, 'confidence': r.confidence, 'ms': r.ms, 'probabilities': r.probabilities})
              if a.json else r)
    elif a.cmd == 'serve':
        from .server import serve
        serve(a.decider, a.host, a.port, a.delay_ms)
    elif a.cmd == 'bench':
        from . import bench
        result = bench.run(a.states, a.url, a.decider, a.name, a.tick_hz, limit=a.limit)
        print(json.dumps(result) if a.json else bench.report(result))
    elif a.cmd == 'train':
        from .train import fit_dir
        d = fit_dir(a.data, a.out, a.steps, a.seed)
        print(json.dumps({'decider': a.out, 'sha256': d.sha256}))
    elif a.cmd == 'list':
        from .core import available
        for name, about in available().items():
            print(f'{name:15s} {about}')


if __name__ == '__main__':
    main()
