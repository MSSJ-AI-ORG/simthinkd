"""Does your decider fit inside one game tick? Measures decision time and teacher agreement on recorded states.

    simthinkd bench                                   # the bundled decider, in-process, bundled Doom states
    simthinkd bench --url http://127.0.0.1:8000/v1/systemone --name my-model
    simthinkd bench --states my_states.json --tick-hz 60

Any server that accepts the decision request (PROTOCOL.md) and answers {"answers": {"operation": {"choice": ...}}}
can be measured. States file: {"rows": [{"body": <request>, "teacher": <action>}, ...]}.
One request at a time; the time is the full round trip seen by the caller.
"""
import json
import statistics
import time
import urllib.request
from pathlib import Path

from .core import Decider

BUNDLED = Path(__file__).resolve().parent / 'data' / 'doom_defend_states.json'


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as reply:
        return json.load(reply)['answers']['operation']['choice']


def run(states=None, url=None, decider='doom-defend', name=None, tick_hz=35.0, warmup=20, limit=0):
    rows = json.loads(Path(states or BUNDLED).read_text(encoding='utf8'))['rows']
    rows = rows[:limit] if limit else rows
    if url:
        call, label = (lambda body: _post(url, body)), name or url
    else:
        d = decider if isinstance(decider, Decider) else Decider(decider)
        call, label = (lambda body: d.predict(body)['operation']['choice']), name or f'simthink-d:{d.preset["name"]}'
    for row in rows[:warmup]:
        call(row['body'])
    times, agree = [], 0
    for row in rows:
        start = time.perf_counter()
        choice = call(row['body'])
        times.append((time.perf_counter() - start) * 1000)
        agree += choice == row['teacher']
    q = sorted(times)
    tick_ms = 1000.0 / tick_hz
    return {'name': label, 'states': len(rows), 'tick_ms': round(tick_ms, 2),
            'p50_ms': round(statistics.median(q), 3), 'p95_ms': round(q[max(0, int(0.95 * len(q)) - 1)], 3),
            'within_one_tick': round(sum(t <= tick_ms for t in times) / len(times), 4),
            'teacher_agreement': round(agree / len(rows), 4)}


def throughput(states=None, decider='doom-defend', sizes=(1, 10, 100, 1000), limit=1000, repeat=3):
    """Decisions per second, one request at a time vs batches (Decider.predict_batch), and where the time goes:
    encoding (text to features, per request) vs the network (one padded pass per batch). In-process only."""
    from .policy import encode
    d = decider if isinstance(decider, Decider) else Decider(decider)
    rows = json.loads(Path(states or BUNDLED).read_text(encoding='utf8'))['rows']
    bodies = [rows[i % len(rows)]['body'] for i in range(limit)]
    d.predict_batch(bodies[:20])
    out = {'name': f'simthink-d:{d.preset["name"]}', 'decisions': len(bodies), 'sizes': {}}
    start = time.perf_counter()
    for body in bodies:
        d.predict(body)
    out['one_at_a_time_per_s'] = round(len(bodies) / (time.perf_counter() - start), 1)
    for size in sizes:
        best = None
        for _ in range(repeat):
            enc_s = net_s = 0.0
            for i in range(0, len(bodies), size):
                chunk = bodies[i:i + size]
                t0 = time.perf_counter()
                encoded = [encode(b) for b in chunk]
                t1 = time.perf_counter()
                scores = d.policy.scores_batch([e[0] for e in encoded])
                [d.policy.decode(e, s) for e, s in zip(encoded, scores)]
                enc_s, net_s = enc_s + t1 - t0, net_s + time.perf_counter() - t1
            if best is None or enc_s + net_s < best[0] + best[1]:
                best = (enc_s, net_s)
        enc_s, net_s = best
        out['sizes'][size] = {'per_s': round(len(bodies) / (enc_s + net_s), 1), 'encode_share': round(enc_s / (enc_s + net_s), 3),
                              'network_only_per_s': round(len(bodies) / net_s, 1)}
    return out


def throughput_report(r):
    lines = [f"{r['name']}: {r['decisions']} decisions, one at a time {r['one_at_a_time_per_s']}/s"]
    for size, v in r['sizes'].items():
        lines.append(f"  batch {size:>5}: {v['per_s']}/s overall, network alone {v['network_only_per_s']}/s, "
                     f"{v['encode_share']:.0%} of the time spent encoding text")
    return '\n'.join(lines)


def report(result):
    return (f"{result['name']}: median {result['p50_ms']} ms, p95 {result['p95_ms']} ms, "
            f"{result['within_one_tick']:.1%} of decisions within one {result['tick_ms']} ms tick, "
            f"teacher agreement {result['teacher_agreement']:.1%} on {result['states']} states")
