#!/usr/bin/env python3
"""Run factory inspection simulator headless.

Outputs to JSON so the web viewer can replay results.

Examples:
    # Run with modelled latency (no decider call)
    python run.py --arm T0 --parts 50

    # Run with local decider at http://127.0.0.1:11890
    python run.py --arm D --parts 50 --expect-sha <hash>

    # Run with two deciders (local + slow)
    python run.py --arm CASCADE --parts 50 --expect-sha <hash> --slow-expect-sha <hash2>
"""
import argparse
import json
import sys
from pathlib import Path

from simulator import Config, Simulation, canonical


def main():
    parser = argparse.ArgumentParser(description='Run factory inspection simulation')
    parser.add_argument('--parts', type=int, default=50, help='Number of parts to inspect')
    parser.add_argument('--arm', default='T0',
                       choices=['T0','S','D','J','CASCADE','RANDOM','INJ','HOLD','SJ'],
                       help='Decider policy')
    parser.add_argument('--seed', type=int, default=910000, help='Random seed')
    parser.add_argument('--line', default='line_A', choices=['line_A','line_B'],
                       help='Production line')
    parser.add_argument('--url', default='http://127.0.0.1:11890',
                       help='Decider HTTP endpoint')
    parser.add_argument('--slow-url', default='http://127.0.0.1:11891',
                       help='Slow decider HTTP endpoint (for cascade)')
    parser.add_argument('--expect-sha', default='',
                       help='Expected weights SHA256 of decider')
    parser.add_argument('--slow-expect-sha', default='',
                       help='Expected weights SHA256 of slow decider')
    parser.add_argument('--mode', default='async', choices=['sync','async'],
                       help='Simulation mode')
    parser.add_argument('--timing', default='modelled', choices=['live','modelled'],
                       help='Use live HTTP or modelled latency')
    parser.add_argument('--belt-speed', type=float, default=1.0,
                       help='Belt speed multiplier')
    parser.add_argument('--tau', type=float, default=0.9,
                       help='Cascade confidence threshold')
    parser.add_argument('--defect-rate', type=float, default=0.08,
                       help='Fraction of parts with defects')
    parser.add_argument('--out', default='result.json',
                       help='Output file for results')
    args = parser.parse_args()

    # If no hash is given, read it from the running decider and print it, so the run records which weights it used.
    if args.arm in ('D', 'CASCADE') and not args.expect_sha:
        import json
        import urllib.request
        with urllib.request.urlopen(args.url.rstrip('/') + '/health', timeout=5) as r:
            args.expect_sha = json.loads(r.read())['weights_sha256']
        print(f'Decider weights SHA256 (from /health): {args.expect_sha}', flush=True)

    config = Config(
        seed=args.seed,
        parts=args.parts,
        arm=args.arm,
        line=args.line,
        url=args.url,
        slow_url=args.slow_url,
        expect_sha=args.expect_sha,
        slow_expect_sha=args.slow_expect_sha,
        mode=args.mode,
        timing=args.timing,
        belt_speed=args.belt_speed,
        tau=args.tau,
        defect_rate=args.defect_rate
    )

    print(f'Running {args.parts} parts with arm={args.arm}...', flush=True)
    sim = Simulation(config)

    try:
        result = sim.run()
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr, flush=True)
        sys.exit(1)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, 'w') as f:
        f.write(canonical(result))

    metrics = result['metrics']
    print(f'Completed {metrics["parts"]} parts', flush=True)
    print(f'  Throughput: {metrics["throughput_parts_per_min"]:.1f} parts/min', flush=True)
    print(f'  Escape rate: {metrics["escape_rate"]:.1%}', flush=True)
    print(f'  False reject rate: {metrics["false_reject_rate"]:.1%}', flush=True)
    print(f'  Late decisions: {metrics["late_rate"]:.1%}', flush=True)
    print(f'  Decision latency P50: {metrics["decision_ms_p50"]:.1f} ms', flush=True)
    print(f'  Correct decisions: {metrics["correct_rate"]:.1%}', flush=True)
    print(f'  Cost: {metrics["cost"]:.0f}', flush=True)
    print(f'', flush=True)
    print(f'Results saved to: {args.out}', flush=True)


if __name__ == '__main__':
    main()
