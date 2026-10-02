"""Line Tempo: simulated inspection conveyor with 400 ms decision deadline.

Runs as headless simulator (no rendering) for the browser viewer to consume.
Operates without any external dependencies or credentials.
"""
from __future__ import annotations
import copy, hashlib, http.client, json, math, os, random, time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit


OPERATIONS = ('PASS', 'REJECT', 'REWORK', 'REINSPECT', 'SLOW_BELT', 'STOP_LINE', 'ESCALATE')
DEFECT_BINS = {'scratch':'BIN_SURFACE', 'dent':'BIN_GEOMETRY', 'missing_screw':'BIN_ASSEMBLY', 'stain':'BIN_CONTAMINATION'}
ACTION_TARGETS = {
    'reject_target': tuple(DEFECT_BINS.values()),
    'reinspect_target': ('SLOW_PASS','SECOND_CAMERA'),
    'slow_belt_target': ('SPEED_90','SPEED_70'),
    'escalate_target': ('HUMAN','SLOW_MODEL')
}


def canonical(value):
    """Deterministic JSON for hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    """SHA256 hash of canonical form."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def make_rng(seed, index, stream):
    """Deterministic PRNG from seed, index, and stream name."""
    key = hashlib.sha256(f'{seed}:{index}:{stream}'.encode()).digest()
    return random.Random(int.from_bytes(key[:8], 'big'))


def action(operation, target=None):
    """Build an action dict."""
    return {'operation': operation, **({operation.lower() + '_target': target} if target else {})}


def check_url(url):
    """Validate HTTP(S) URL for decider calls."""
    p = urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('URL must use HTTP(S) without embedded credentials, query, or fragment')
    if p.scheme == 'http' and p.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('Remote deciders require HTTPS')
    _ = p.port
    return p


@dataclass
class Config:
    """Simulation configuration."""
    seed: int = 910000
    parts: int = 500
    line: str = 'line_A'
    arm: str = 'T0'
    base_arm: str = 'D'
    mode: str = 'async'
    timing: str = 'modelled'
    tick_hz: int = 50
    belt_speed: float = 1.0
    spacing_m: float = .24
    window_m: float = .4
    defect_rate: float = .08
    novelty_rate: float = 0.0
    detection: float = .96
    false_alarm: float = .01
    severity_noise: float = .03
    blur: float = .02
    drift: float = 0.0
    tau: float = .9
    local_ms: float = 2.0
    slow_ms: float = 600.0
    jitter_ms: float = 0.0
    inject_ms: float = 0.0
    hold_ticks: int = 10
    stop_ticks: int = 50
    default_action: str = 'PASS'
    bin_capacity: int = 40
    hold_capacity: int = 20
    rework_capacity: int = 12
    buffer_capacity: int = 12
    rework_ms: float = 1200.0
    packing_ms: float = 200.0
    human_ms: float = 2000.0
    bin_service_ms: float = 3000.0
    url: str = 'http://127.0.0.1:11890'
    slow_url: str = 'http://127.0.0.1:11891'
    expect_sha: str = ''
    slow_expect_sha: str = ''
    timeout_s: float = 10.0
    latencies: list = field(default_factory=list)
    costs: dict = field(default_factory=lambda: dict(escape=100., false_reject=20., stop=10., escalation=5., rework=1.))

    def validate(self):
        """Check all configuration values."""
        for k in ('parts','tick_hz','hold_ticks','stop_ticks','bin_capacity','hold_capacity','rework_capacity','buffer_capacity'):
            v = getattr(self, k)
            if type(v) is not int or v < 1:
                raise ValueError(f'{k} must be a positive integer')
        if type(self.seed) is not int or self.parts > 100000 or self.tick_hz > 1000:
            raise ValueError('Invalid seed or run size')
        if self.line not in ('line_A','line_B') or self.mode not in ('sync','async') or self.timing not in ('live','modelled'):
            raise ValueError('Invalid line, mode, or timing')
        if self.arm not in ('T0','S','D','J','SJ','CASCADE','INJ','HOLD','RANDOM'):
            raise ValueError('Invalid arm')
        if self.base_arm not in ('T0','S','D','J'):
            raise ValueError('Invalid base_arm')
        if self.default_action not in ('PASS','HOLD'):
            raise ValueError('Invalid fallback')
        for k in ('belt_speed','spacing_m','window_m','timeout_s','rework_ms','packing_ms','human_ms','bin_service_ms'):
            v = getattr(self, k)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v <= 0:
                raise ValueError(f'{k} must be positive and finite')
        for k in ('local_ms','slow_ms','jitter_ms','inject_ms','defect_rate','novelty_rate','detection','false_alarm','severity_noise','blur','drift','tau'):
            v = getattr(self, k)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v < 0:
                raise ValueError(f'{k} must be nonnegative and finite')
        for k in ('defect_rate','novelty_rate','detection','false_alarm','severity_noise','blur','drift','tau'):
            if getattr(self, k) > 1:
                raise ValueError(f'{k} must be a probability')
        if set(self.costs) != {'escape','false_reject','stop','escalation','rework'}:
            raise ValueError('Unknown or missing cost weights')
        if any(not math.isfinite(v) or v < 0 for v in self.costs.values()):
            raise ValueError('Invalid cost weights')
        check_url(self.url)
        check_url(self.slow_url)
        return self


def truth(c, i):
    """Generate ground truth for part i."""
    r = make_rng(c.seed, i, 'truth')
    d = r.choice(tuple(DEFECT_BINS)) if r.random() < c.defect_rate else 'none'
    if r.random() < c.novelty_rate:
        d = 'unknown_pattern'
    family = 'housing' if c.line == 'line_A' else ('housing','bracket','bottle')[i%3]
    return dict(
        id=f'{c.line}:{c.seed}:{i:06d}',
        index=i,
        family=family,
        true_defect=d,
        true_severity=r.choice(('minor','moderate','severe')) if d != 'none' else 'none',
        size=r.choice(('small','medium','large')),
        location=r.choice(('edge','center','surface'))
    )


def teacher_action(part):
    """Ground truth action for a part."""
    d = part['true_defect']
    if d == 'none':
        return action('PASS')
    if d == 'unknown_pattern':
        return action('ESCALATE', 'HUMAN')
    if part['true_severity'] == 'minor' or (d == 'stain' and part['true_severity'] == 'moderate'):
        return action('REWORK')
    return action('REJECT', DEFECT_BINS[d])


def observe(c, part, state):
    """Generate observation sentence for a part."""
    r = make_rng(c.seed, part['index'], 'perception')
    d = part['true_defect']
    sev = part['true_severity']
    drift = c.drift * part['index'] / max(1, c.parts - 1)
    factor = {'scratch':.96,'dent':.98,'missing_screw':.99,'stain':.96,'unknown_pattern':.92}.get(d, 1)
    factor *= {'small':.94,'medium':.98,'large':1}[part['size']]

    if d != 'none' and r.random() > max(0, c.detection * factor - drift * .3):
        d = 'none'
        sev = 'none'
    if d == 'none' and r.random() < c.false_alarm:
        d = r.choice(tuple(DEFECT_BINS))
        sev = 'minor'
    if sev != 'none' and r.random() < c.severity_noise:
        sev = r.choice(('minor','moderate','severe'))

    blurry = r.random() < min(1, c.blur + max(0, state['speed'] - 1) * .2 + drift)
    speed = 'slow' if state['speed'] < .9 else 'fast' if state['speed'] > 1.1 else 'normal'
    spacing = 'tight' if c.spacing_m < .2 else 'wide' if c.spacing_m > .4 else 'normal'
    hold = min(100, 10 * int(10 * state['hold'] / c.hold_capacity))

    sentence = (f"part: family {part['family']} | defect {d} | size {part['size']} | location {part['location']} | "
                f"severity {sev} | image {'blurry' if blurry else 'clear'} | line: belt {speed} | spacing {spacing} | "
                f"rework queue {'long' if state['rework'] >= c.rework_capacity/2 else 'short'} | hold bin {hold}% | "
                f"last 10 parts {state['rejects']} rejects")
    return sentence + (' | shape streak | texture irregular' if d == 'unknown_pattern' else '')


def build_request(sentence, line='line_A', tick=0):
    """Create a decision request for the decider."""
    return {
        'model': 'line_tempo_v1',
        'state': {
            'page': {
                'url': f'sim://line_tempo/{line}',
                'title': f'tick {tick}',
                'text': sentence
            },
            'elements': [{'id': o, 'role': 'button', 'label': o} for o in OPERATIONS],
            'recent_actions': []
        },
        'questions': {
            'operation': {
                'type': 'choice',
                'criteria': {o: o for o in OPERATIONS},
                'instructions': {'goal': 'Ship good parts before the decision deadline.'}
            },
            **{k: {'type': 'choice', 'criteria': {v: v for v in values}}
              for k, values in ACTION_TARGETS.items()}
        }
    }


def decode_decision(reply, request):
    """Extract action and confidence from decider reply."""
    def one(key):
        a = reply['answers'][key]
        offered = request['questions'][key]['criteria']
        choice = a['choice']
        probs = a['probabilities']
        confidence = a['confidence']

        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('Invalid confidence')
        if choice not in offered or set(probs) != set(offered):
            raise ValueError('Unrecognized choice or probabilities')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in probs.values()):
            raise ValueError('Invalid probabilities')
        if not math.isclose(sum(probs.values()), 1, abs_tol=1e-4) or not math.isclose(confidence, probs[choice], abs_tol=1e-4):
            raise ValueError('Probability/confidence mismatch')
        return choice, confidence

    op, conf = one('operation')
    key = op.lower() + '_target'
    target = one(key)[0] if key in request['questions'] else None
    return action(op, target), conf


class DeciderClient:
    """HTTP client for calling remote decider."""
    def __init__(self, url, expected_sha, timeout=10.):
        p = check_url(url)
        self.expected = expected_sha
        self.timeout = timeout
        self.path = p.path.rstrip('/')
        cls = http.client.HTTPSConnection if p.scheme == 'https' else http.client.HTTPConnection
        self.cls = cls
        self.host = (p.hostname, p.port)
        self.conn = cls(p.hostname, p.port, timeout=timeout)
        self.headers = {'Content-Type': 'application/json'}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='decider')

        try:
            health = self.exchange('GET', '/health')
            if health.get('weights_sha256') != expected_sha:
                raise ValueError('Health check SHA256 mismatch')
        except Exception:
            self.close()
            raise

    def exchange(self, method, path, payload=None):
        """Make HTTP request to decider."""
        try:
            self.conn.request(
                method,
                self.path + path,
                None if payload is None else canonical(payload).encode(),
                self.headers
            )
            r = self.conn.getresponse()
            raw = r.read(2_000_001)
            if r.status != 200 or len(raw) > 2_000_000:
                raise ValueError('HTTP status or size invalid')
            return json.loads(raw)
        except Exception:
            self.conn.close()
            raise

    def submit(self, request_payload, start_time, deadline_ms):
        """Submit decision request async."""
        def call():
            sent = time.perf_counter()
            try:
                if (sent - start_time) * 1000 >= deadline_ms:
                    raise TimeoutError('Expired in queue')
                reply = self.exchange('POST', '/v1/systemone', request_payload)
                if reply.get('meta', {}).get('weights_sha256') != self.expected:
                    raise ValueError('Response SHA256 mismatch')
                a, conf = decode_decision(reply, request_payload)
                return dict(
                    action=a, confidence=conf, at=(time.perf_counter() - start_time) * 1000,
                    http_ms=(time.perf_counter() - sent) * 1000, invalid=False
                )
            except Exception as e:
                return dict(
                    action=None, confidence=None, at=(time.perf_counter() - start_time) * 1000,
                    invalid=True, error=type(e).__name__
                )
        return self.pool.submit(call)

    def close(self):
        """Shutdown client."""
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.conn.close()


class Simulation:
    """Conveyor line simulation."""
    def __init__(self, config):
        self.c = config.validate()
        self.dt = 1000 / self.c.tick_hz
        self.tick = 0
        self.parts = []
        self.active = []
        self.pending = []
        self.clients = {}
        self.busy = {'local': 0., 'slow': 0.}
        self.state = dict(speed=self.c.belt_speed, rework=0, hold=0, rejects=0)
        self.queues = {'rework': [], 'hold': [], 'packing': []}
        self.bins = {b: 0 for b in DEFECT_BINS.values()}
        self.bin_due = {}
        self.recent = deque(maxlen=10)
        self.infeed = 0.
        self.finished = 0
        self.stop_until = 0
        self.speed_until = 0
        self.counts = dict(
            ticks_waiting=0, line_stops=0, human_escalations=0, slow_model_calls=0, invalid=0,
            rework_load=0, capacity_overflow=0, agv_services=0, backpressure_ticks=0, cascade_escalations=0
        )
        self.started = 0.
        self.max_lag = 0.
        self.end_ms = 0.
        self.belt_travel = 0.
        self.timeline = []

    @property
    def now(self):
        return self.tick * self.dt

    @property
    def arm(self):
        return self.c.base_arm if self.c.arm in ('INJ','HOLD') else self.c.arm

    def connect(self):
        """Connect to remote decider if live mode."""
        if self.c.timing != 'live':
            return
        if self.arm in ('S','D','CASCADE'):
            self.clients['local'] = DeciderClient(self.c.url, self.c.expect_sha, self.c.timeout_s)
        if self.arm in ('J','CASCADE'):
            url = self.c.slow_url if self.arm == 'CASCADE' else self.c.url
            sha = self.c.slow_expect_sha if self.arm == 'CASCADE' else self.c.expect_sha
            self.clients['slow'] = DeciderClient(url, sha, self.c.timeout_s)

    def call(self, p, channel):
        """Submit part to decider."""
        c = self.c
        now = self.now
        if channel == 'slow':
            self.counts['slow_model_calls'] += 1

        item = dict(
            id=p['index'], channel=channel, sent_at=now,
            expires=now + c.timeout_s * 1000
        )

        if channel in self.clients:
            item['future'] = self.clients[channel].submit(
                p['request'], self.started, item['expires']
            )
        else:
            delay = 0. if self.arm == 'T0' else c.slow_ms if channel == 'slow' else c.local_ms
            if self.arm != 'T0':
                delay = max(0, delay + make_rng(c.seed, p['index'], 'latency-' + channel).uniform(-c.jitter_ms, c.jitter_ms))
            due = now + delay
            self.busy[channel] = due
            if c.arm == 'INJ':
                due += c.inject_ms

            a, conf = teacher_action(p), 1.
            if self.arm in ('S','T0'):
                a = p['teacher_action']
            if self.arm == 'RANDOM':
                r = make_rng(c.seed, p['index'], 'random_policy')
                op = r.choice(('PASS','REJECT','REWORK'))
                a = action(op, r.choice(tuple(DEFECT_BINS.values())) if op == 'REJECT' else None)
                conf = 1/3

            item['answer'] = dict(
                action=a, confidence=conf, invalid=due > item['expires'],
                at=min(due, item['expires']), http_ms=None
            )

        self.pending.append(item)

    def spawn(self):
        """Create new part."""
        p = truth(self.c, len(self.parts))
        self.state['rejects'] = sum(self.recent)
        p.update(
            camera_at_ms=self.now, camera_travel_m=self.belt_travel, distance=0.,
            sentence=observe(self.c, p, self.state), teacher_action=teacher_action(p),
            decided_action=None, decided_at_ms=None, confidence=None,
            arrived_at_diverter_ms=None, applied_action=None, late=False, invalid=False,
            correct=None, arm=self.c.arm, route=None, responses=[], shipped=False,
            defect_shipped=False
        )
        p['request'] = build_request(p['sentence'], self.c.line, self.tick)
        self.parts.append(p)
        self.active.append(p['index'])

        if self.arm == 'T0' and not (self.c.arm == 'INJ' and self.c.inject_ms):
            self.answer(p, dict(action=p['teacher_action'], confidence=1., at=self.now, invalid=False), 'teacher', self.now)
        else:
            self.call(p, 'slow' if self.arm == 'J' else 'local')

    def answer(self, p, a, channel, sent):
        """Record decision for a part."""
        applied = math.ceil((a['at'] - 1e-7) / self.dt) * self.dt
        p['responses'].append({
            **a, 'stage': channel, 'sent_at_ms': sent, 'applied_tick_ms': applied
        })
        if a['invalid']:
            p['invalid'] = True
            self.counts['invalid'] += 1
            return

        candidate = p['teacher_action'] if self.arm in ('S',) else a['action']
        if p['arrived_at_diverter_ms'] is None or p['decided_action'] is None:
            p['decided_action'] = copy.deepcopy(candidate)
            p['decided_at_ms'] = applied
            p['confidence'] = a['confidence']

        if self.arm == 'CASCADE' and channel == 'local' and a['confidence'] < self.c.tau and p['arrived_at_diverter_ms'] is None:
            self.counts['cascade_escalations'] += 1
            self.call(p, 'slow')

    def collect(self):
        """Collect ready decisions from pending requests."""
        waiting = []
        ready = []

        for item in self.pending:
            if 'future' in item:
                f = item['future']
                if f.done():
                    a = f.result()
                    if self.c.arm == 'INJ':
                        a['at'] += self.c.inject_ms
                    item.pop('future')
                    item['answer'] = a
                elif self.now >= item['expires']:
                    f.cancel()
                    item.pop('future')
                    item['answer'] = dict(at=self.now, invalid=True, action=None, confidence=None, error='TimeoutError')

            a = item.get('answer')
            if a and a['at'] <= self.now + 1e-7:
                ready.append((item, a))
            else:
                waiting.append(item)

        self.pending = waiting
        for item, a in ready:
            self.answer(self.parts[item['id']], a, item['channel'], item['sent_at'])

    def enqueue(self, name, p, delay):
        """Add part to queue."""
        q = self.queues[name]
        due = max(self.now, q[-1][0] if q else self.now) + delay
        q.append([due, p['index']])
        p['service_due_ms'] = due
        if name in self.state:
            self.state[name] = len(q)

    def pack(self, p):
        """Ship a part."""
        if self.c.line == 'line_A':
            p['shipped'] = True
            p['defect_shipped'] = p.get('residual_defect', p['true_defect'] != 'none')
            p['packed_at_ms'] = self.now
        else:
            self.enqueue('packing', p, self.c.packing_ms)

    def hold(self, p):
        """Hold a part for human review."""
        p['route'] = 'HOLD'
        if len(self.queues['hold']) >= self.c.hold_capacity:
            self.counts['capacity_overflow'] += 1
            p['route'] = 'OVERFLOW_QUARANTINE'
            return
        self.enqueue('hold', p, self.c.human_ms)

    def service(self):
        """Process queue services and bin empties."""
        for b, due in list(self.bin_due.items()):
            if self.now >= due:
                self.bins[b] = 0
                del self.bin_due[b]
                self.counts['agv_services'] += 1

        for name in ('packing','hold','rework'):
            left = []
            for due, i in self.queues[name]:
                p = self.parts[i]
                if due > self.now:
                    left.append([due, i])
                    continue
                if name == 'packing':
                    p['shipped'] = True
                    p['defect_shipped'] = p.get('residual_defect', p['true_defect'] != 'none')
                    p['packed_at_ms'] = self.now
                elif name == 'hold':
                    p['postprocess'] = 'retained_for_disposition'
                    p['postprocess_at_ms'] = self.now
                elif p.get('repairable'):
                    if self.c.line == 'line_B' and len(self.queues['packing']) >= self.c.buffer_capacity:
                        left.append([due, i])
                        continue
                    p['residual_defect'] = False
                    p['postprocess'] = 'repaired'
                    p['postprocess_at_ms'] = self.now
                    self.pack(p)
                else:
                    p['postprocess'] = 'unrepairable_quarantine'
                    p['postprocess_at_ms'] = self.now
            self.queues[name] = left
            if name in self.state:
                self.state[name] = len(left)

        if self.tick >= self.speed_until:
            self.state['speed'] = self.c.belt_speed

    def optimal(self, p):
        """Calculate optimal action (ground truth with bin capacity)."""
        if p['true_defect'] == 'none':
            return action('PASS')
        if p['true_defect'] == 'unknown_pattern':
            return action('ESCALATE', 'HUMAN')
        b = DEFECT_BINS[p['true_defect']]
        return action('REJECT', b) if self.bins[b] < self.c.bin_capacity else action('ESCALATE', 'HUMAN')

    def route(self, p):
        """Apply decision and route part."""
        c = self.c
        p['arrived_at_diverter_ms'] = self.now
        valid = p['decided_at_ms'] is not None and p['decided_at_ms'] < self.now
        timely_error = any(a['invalid'] and a['applied_tick_ms'] < self.now for a in p['responses'])
        p['late'] = not valid and not timely_error

        a = copy.deepcopy(p['decided_action'] if valid else action(c.default_action))
        p['applied_action'] = a
        p['optimal_action'] = self.optimal(p)
        p['correct'] = a == p['optimal_action']

        op = a['operation']
        self.recent.append(op == 'REJECT')

        if op == 'PASS':
            p['route'] = 'PACK'
            self.pack(p)
        elif op == 'REJECT':
            b = a['reject_target']
            p['route'] = b
            if self.bins[b] >= c.bin_capacity:
                self.counts['capacity_overflow'] += 1
                self.hold(p)
            else:
                self.bins[b] += 1
                if self.bins[b] == c.bin_capacity:
                    self.bin_due[b] = self.now + c.bin_service_ms
        elif op == 'REWORK':
            self.counts['rework_load'] += 1
            if len(self.queues['rework']) >= c.rework_capacity:
                self.counts['capacity_overflow'] += 1
                self.hold(p)
            else:
                p['route'] = 'REWORK'
                p['repairable'] = (
                    p['true_defect'] == 'none' or p['true_severity'] == 'minor' or
                    (p['true_defect'] == 'stain' and p['true_severity'] == 'moderate')
                )
                self.enqueue('rework', p, c.rework_ms)
        else:
            self.hold(p)
            if op == 'ESCALATE' and a.get('escalate_target') == 'HUMAN':
                self.counts['human_escalations'] += 1
            if op == 'STOP_LINE':
                self.stop_until = self.tick + (c.hold_ticks if c.arm == 'HOLD' else c.stop_ticks)
                self.counts['line_stops'] += 1
            if op == 'SLOW_BELT':
                speed_factor = .7 if a['slow_belt_target'] == 'SPEED_70' else .9
                self.state['speed'] = c.belt_speed * speed_factor
                self.speed_until = self.tick + c.hold_ticks

        self.finished += 1
        self.end_ms = self.now

    def step(self):
        """Simulation step."""
        self.service()
        self.collect()

        waiting = any(
            self.parts[i]['decided_at_ms'] is None and not self.parts[i]['invalid']
            for i in self.active
        )
        if waiting:
            self.counts['ticks_waiting'] += 1

        backpressure = self.c.line == 'line_B' and len(self.queues['packing']) >= self.c.buffer_capacity
        if backpressure:
            self.counts['backpressure_ticks'] += 1

        pause = (
            self.tick < self.stop_until or backpressure or
            (self.c.mode == 'sync' and any(x['id'] in self.active for x in self.pending))
        )

        if not pause:
            dx = self.state['speed'] * self.dt / 1000
            self.belt_travel += dx
            for i in list(self.active):
                p = self.parts[i]
                p['distance'] += dx
                if p['distance'] + 1e-9 >= self.c.window_m:
                    self.route(p)
                    self.active.remove(i)

            if self.parts:
                self.infeed += dx
            if not self.parts:
                self.spawn()
                self.infeed = 0.
            else:
                while (self.infeed + 1e-9 >= self.c.spacing_m and
                       len(self.parts) < self.c.parts and
                       not (self.c.mode == 'sync' and self.active)):
                    self.infeed -= self.c.spacing_m
                    self.spawn()
            self.collect()

        self.timeline.append([self.now, self.belt_travel])
        self.tick += 1

    def run(self):
        """Run full simulation."""
        try:
            self.connect()
            self.started = time.perf_counter() - self.now / 1000
            limit = int((
                self.c.parts * (self.c.timeout_s + self.c.spacing_m / self.c.belt_speed + self.c.human_ms / 1000) + 120
            ) * self.c.tick_hz)

            while self.finished < self.c.parts:
                if self.c.timing == 'live':
                    deadline = self.started + self.now / 1000
                    time.sleep(max(0, deadline - time.perf_counter()))
                    self.max_lag = max(self.max_lag, (time.perf_counter() - deadline) * 1000)

                self.step()
                if self.tick > limit:
                    raise RuntimeError('Progress watchdog exceeded')

            return self.result()
        finally:
            for client in self.clients.values():
                client.close()

    def result(self):
        """Generate simulation results."""
        rows = self.parts
        c = self.c
        defects = sum(p['true_defect'] != 'none' for p in rows)
        good = len(rows) - defects
        escapes = sum(p['defect_shipped'] for p in rows)
        false = sum(
            p['true_defect'] == 'none' and p['applied_action']['operation'] == 'REJECT'
            for p in rows
        )

        lat = sorted(
            p['decided_at_ms'] - p['camera_at_ms'] for p in rows
            if p['decided_at_ms'] is not None
        )

        def percentile(q):
            if not lat:
                return None
            f = (len(lat) - 1) * q
            lo = int(f)
            return lat[lo] + (lat[min(lo + 1, len(lat) - 1)] - lat[lo]) * (f - lo)

        count = copy.deepcopy(self.counts)
        metrics = dict(
            parts=len(rows),
            defective_parts=defects,
            escape_count=escapes,
            escape_rate=escapes / max(1, defects),
            false_reject_count=false,
            false_reject_rate=false / max(1, good),
            late_rate=sum(p['late'] for p in rows) / len(rows),
            throughput_parts_per_min=len(rows) * 60000 / max(self.dt, self.end_ms),
            elapsed_ms=self.end_ms,
            shipped_parts=sum(p['shipped'] for p in rows),
            decision_ms_p50=percentile(.5),
            decision_ms_p90=percentile(.9),
            decision_latency_samples=len(lat),
            pending_calls_at_end=len(self.pending),
            queue_at_end={k: len(q) for k, q in self.queues.items()},
            max_wall_lag_ms=self.max_lag if c.timing == 'live' else None,
            correct_rate=sum(p['correct'] for p in rows) / len(rows),
            **count
        )

        metrics['cost'] = (
            escapes * c.costs['escape'] +
            false * c.costs['false_reject'] +
            count['line_stops'] * c.costs['stop'] +
            count['human_escalations'] * c.costs['escalation'] +
            count['rework_load'] * c.costs['rework']
        )

        return dict(
            schema_version='line_tempo_reference/0.2',
            engine='Python reference',
            config=asdict(c),
            metrics=metrics,
            per_part=copy.deepcopy(rows),
            timeline=copy.deepcopy(self.timeline)
        )
