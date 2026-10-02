#!/usr/bin/env python3
"""Train an inspection decider with SimThink D.

Trains a small model (no pretrained weights) using a rule teacher that matches
the simulator's ground truth. The trained decider can then be served with:

    simthinkd serve factory_inspection --port 11890

Example:
    python train_inspection_decider.py --out models/factory_inspection --steps 600
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import simthinkd
except ImportError:
    print('Error: simthinkd not installed. Install with: pip install -e .', file=sys.stderr)
    sys.exit(1)

from simulator import Config, Simulation, teacher_action, canonical


def main():
    parser = argparse.ArgumentParser(description='Train an inspection decider')
    parser.add_argument('--out', default='models/factory_inspection',
                       help='Output folder for trained weights')
    parser.add_argument('--steps', type=int, default=600,
                       help='Training steps')
    parser.add_argument('--parts', type=int, default=200,
                       help='Number of parts to generate examples from')
    parser.add_argument('--seed', type=int, default=910000,
                       help='Random seed')
    args = parser.parse_args()

    out = Path(args.out)

    print(f'Generating {args.parts} training examples...', flush=True)

    examples = []
    config = Config(seed=args.seed, parts=args.parts, arm='T0', timing='modelled')
    sim = Simulation(config)

    while len(sim.parts) < args.parts:
        sim.spawn()
        sim.service()
        sim.step()

    for p in sim.parts[:args.parts]:
        sentence = p['sentence']
        teacher = p['teacher_action']
        op = teacher['operation']

        examples.append({
            'state': sentence,
            'action': op
        })

    print(f'Training {len(examples)} examples with SimThink D...', flush=True)

    actions = {
        'PASS': 'Ship this part as-is.',
        'REJECT': 'Reject to bin (choose which).',
        'REWORK': 'Route to repair queue.',
        'REINSPECT': 'Slow camera for second look.',
        'SLOW_BELT': 'Slow belt speed (choose 90% or 70%).',
        'STOP_LINE': 'Stop line immediately.',
        'ESCALATE': 'Hold for human (choose Human or Slow Model).',
    }

    goal = 'Ship good parts and contain defects before the 400 ms decision deadline.'

    try:
        decider = simthinkd.fit(
            examples,
            actions,
            goal=goal,
            out=out,
            steps=args.steps
        )
    except TypeError:
        print('Fitting with legacy API...', flush=True)
        decider = simthinkd.fit(examples, actions, out)

    print(f'Decider trained: {out}', flush=True)
    print(f'SHA256: {decider.sha256}', flush=True)
    print(f'', flush=True)
    print(f'To serve this decider on port 11890:', flush=True)
    print(f'  simthinkd serve factory_inspection --port 11890', flush=True)
    print(f'', flush=True)
    print(f'Then in another terminal:', flush=True)
    print(f'  python run.py --arm D --parts 50', flush=True)


if __name__ == '__main__':
    main()
