"""High-level API: load a decider, ask it for one action, get the choice, probabilities and time.

    from simthinkd import Decider
    d = Decider("doom-defend")
    print(d.decide("seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25"))

A decider is a weights file (about 1 MB, 265,665 parameters) plus the action set and goal it was trained with
(a "preset"). Your own deciders come from `simthinkd.fit(...)`; they carry their preset inside the weights folder.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .policy import Policy

WEIGHTS = Path(__file__).resolve().parent / 'weights'

DOOM_DEFEND_ACTIONS = {
    'TURN_LEFT': 'Turn left toward the target.',
    'TURN_RIGHT': 'Turn right toward the target.',
    'ATTACK': 'Shoot now, standing still.',
    'STRAFE_LEFT': 'Sidestep left without shooting.',
    'STRAFE_RIGHT': 'Sidestep right without shooting.',
    'ATTACK_STRAFE_LEFT': 'Shoot while sidestepping left.',
    'ATTACK_STRAFE_RIGHT': 'Shoot while sidestepping right.',
}
DOOM_CORRIDOR_ACTIONS = {
    'MOVE_LEFT': 'Sidestep left, away from fire.',
    'MOVE_RIGHT': 'Sidestep right, away from fire.',
    'ATTACK': 'Shoot now; an enemy is lined up ahead.',
    'MOVE_FORWARD': 'Advance down the corridor toward the armor.',
    'MOVE_BACKWARD': 'Back off from what is in front.',
    'TURN_LEFT': 'Turn left toward something on the left.',
    'TURN_RIGHT': 'Turn right toward something on the right.',
}

PRESETS = {
    'doom-defend': {
        'weights': 'doom-defend.npz',
        'sha256': 'a814587e03478f451f1ab478558de7e076dbe9a3de9cb2ee4cc84124cdfa2a19',
        'model': 'doom-showcase-s1', 'url': 'doom://defend_the_center/showcase', 'title': 'defend the center tick {tick}',
        'goal': 'Aim, shoot and sway to survive the horde.', 'actions': DOOM_DEFEND_ACTIONS,
        'about': 'ViZDoom defend_the_center: aim, shoot and sway against a horde.',
        'example': 'seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25',
    },
    'doom-corridor': {
        'weights': 'doom-corridor.npz',
        'sha256': 'a164d90514f172ff2f1ac9452aaf83a637ffd8ef3136d0f553179e5c7ab035d8',
        'model': 'doom-corridor', 'url': 'doom://deadly_corridor', 'title': 'deadly corridor tick {tick}',
        'goal': 'Clear the corridor and reach the green armor.', 'actions': DOOM_CORRIDOR_ACTIONS,
        'about': 'ViZDoom deadly_corridor: clear the corridor and reach the armor.',
        'example': 'enemies: ShotgunGuy left near offset15 ; Zombieman right near offset15 | goal: armor ahead distant | body healthy | ammo stocked',
    },
}


def build_request(state, actions, goal, *, url='sim://custom', title='', model='simthinkd', recent_actions=None):
    """Turn (situation sentence, {action: description}, goal) into a decision request (see PROTOCOL.md)."""
    if not isinstance(state, str) or not state.strip():
        raise ValueError('state must be a non-empty sentence describing the situation')
    if not actions or len(actions) > 8:
        raise ValueError('offer between 1 and 8 actions')
    return {
        'model': model,
        'state': {'page': {'url': url, 'title': title, 'text': state},
                  'elements': [{'id': name, 'role': 'button', 'label': name} for name in actions],
                  'recent_actions': list(recent_actions or [])},
        'questions': {'operation': {'type': 'choice',
                                    'criteria': {name: {'element': f'[button] {name}', 'description': why}
                                                 for name, why in actions.items()},
                                    'instructions': {'goal': goal}}},
    }


def answer(policy, body):
    """Reply `answers` block for a protocol request (operation, and `<op>_target` when targets were offered)."""
    chosen, op, conditional, joint, rows, operations = policy.predict(body)
    op_probs = {key: float(op[i]) for i, key in enumerate(operations)}
    top = max(op_probs, key=op_probs.get)
    answers = {'operation': {'choice': top, 'probabilities': op_probs, 'confidence': op_probs[top]}}
    group = operations.index(top)
    targets = [(r['target'], float(joint[i])) for i, r in enumerate(rows) if r['group'] == group and r['target'] is not None]
    if targets:
        total = sum(p for _, p in targets) or 1.0
        probs = {t: p / total for t, p in targets}
        best = max(probs, key=probs.get)
        answers[top.lower() + '_target'] = {'choice': best, 'probabilities': probs, 'confidence': probs[best]}
    return answers


@dataclass(frozen=True)
class Decision:
    choice: str
    confidence: float
    probabilities: dict = field(repr=False)
    ms: float = 0.0

    def __str__(self):
        return f'{self.choice} ({self.confidence:.0%}, {self.ms:.2f} ms)'


class Decider:
    """A trained decider. `Decider("doom-defend")`, `Decider("path/to/folder_or.npz")`."""

    def __init__(self, name_or_path='doom-defend'):
        preset = PRESETS.get(name_or_path)
        if preset:
            path = WEIGHTS / preset['weights']
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != preset['sha256']:
                raise RuntimeError(f'weights file {path.name} does not match its recorded SHA-256')
            self.preset = dict(preset, name=name_or_path)
        else:
            path = Path(name_or_path)
            if path.is_dir():
                card = json.loads((path / 'decider.json').read_text(encoding='utf8'))
                self.preset = dict(card, name=card.get('name', path.name))
                path = path / card['weights']
            else:
                self.preset = {'name': path.stem, 'actions': None, 'goal': '', 'url': 'sim://custom', 'title': '',
                               'model': path.stem}
        self.policy = Policy(path)
        self.sha256 = self.policy.digest

    @property
    def actions(self):
        return dict(self.preset['actions'] or {})

    def request(self, state, actions=None, goal=None, tick=0, recent_actions=None):
        actions = actions or self.preset['actions']
        if not actions:
            raise ValueError('this decider has no stored action set; pass actions={name: description}')
        return build_request(state, actions, self.preset['goal'] if goal is None else goal,
                             url=self.preset.get('url', 'sim://custom'),
                             title=self.preset.get('title', '').format(tick=tick),
                             model=self.preset.get('model', 'simthinkd'), recent_actions=recent_actions)

    def predict(self, body):
        """Protocol-level call: request dict in, `answers` dict out (same as the HTTP server)."""
        return answer(self.policy, body)

    def decide(self, state, actions=None, goal=None, tick=0, recent_actions=None):
        """One decision for one situation sentence. Returns a Decision (choice, confidence, probabilities, ms)."""
        body = self.request(state, actions, goal, tick, recent_actions)
        start = time.perf_counter()
        op = answer(self.policy, body)['operation']
        ms = (time.perf_counter() - start) * 1000
        return Decision(op['choice'], op['confidence'], op['probabilities'], ms)

    def __repr__(self):
        return f'Decider({self.preset["name"]!r}, sha256={self.sha256[:12]})'


def available():
    """Names of the deciders that ship with the package."""
    return {name: p['about'] for name, p in PRESETS.items()}
