"""Relearning loop: when the router hands over too often, ask the teacher (a large model) about those cases, retrain the
decider on old + new examples, hot-swap it into the router, and append one line to a log.

    from simthinkd import HandoffMonitor, Router, relearn
    router = Router(decider, skills, monitor=HandoffMonitor())          # sealed v2.2 trigger: 10 routes, rate 0.5, 3 no-progress
    ...                                                                 # route as usual
    if router.monitor.fired:
        report = relearn(router, teacher, router.take_handed_over() + more_observations,
                         base_examples=old_examples, out='models/router_v2', log='relearn.jsonl')

`teacher(observation)` returns the label the decider should have given (a state name), or None to skip that case. The
teacher is your large model or a person; this module never calls a network itself. Labels must stay within 8 in total
(the decider's limit). Training is `simthinkd.fit` (needs simthinkd[train]); pass `trainer=` to use your own.

Measured in experiment v2.2 (a redesigned sign-in site): 36 teacher calls over 12 runs, then about 10 s of CPU training.
"""
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from .router import SkillTable

RELEARN_SCHEMA = 'simthinkd-relearn/1'


@dataclass(frozen=True)
class RelearnReport:
    at: str
    trigger: dict
    teacher_calls: int
    teacher_skipped: int
    new_examples: int
    examples: int
    labels: tuple
    teach_seconds: float
    train_seconds: float
    old_sha256: str
    new_sha256: str
    out: str

    def to_dict(self):
        return dict(asdict(self), schema=RELEARN_SCHEMA, labels=list(self.labels))


def relearn(router, teacher, observations, base_examples=(), out='relearned', *, steps=600, seed=31, log=None,
            skills=None, trainer=None, force=False, quiet=True):
    """Teacher labels -> retrain -> hot-swap -> log. Returns a RelearnReport; the router now uses the new decider.

    observations: what the router saw (anything its adapter reads; read once). base_examples: the (sentence, label)
    pairs the current decider was trained on (read once), so the new decider keeps what the old one knew.
    skills: optional SkillTable (or mapping) merged into router.skills, e.g. new expected states after a redesign.
    force: relearn even though the router's monitor has not fired (refused otherwise)."""
    monitor = getattr(router, 'monitor', None)
    if monitor is not None and not monitor.fired and not force:
        raise ValueError('the hand-over monitor has not fired; pass force=True to relearn anyway')
    if not callable(teacher):
        raise ValueError('teacher must be callable: observation -> label (or None to skip)')
    observations = list(observations)
    if not observations:
        raise ValueError('relearn needs at least one observation to ask the teacher about')
    base = []
    for i, item in enumerate(base_examples):
        try:
            sentence, label = item
        except (TypeError, ValueError):
            raise ValueError(f'base example {i}: expected (sentence, label), got {item!r}') from None
        base.append((sentence, label))
    trigger = dict(monitor.state() if monitor is not None else {}, forced=bool(force))
    started = time.perf_counter()
    new, skipped = [], 0
    for i, observation in enumerate(observations):
        label = teacher(observation)
        if label is None:
            skipped += 1
            continue
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f'teacher answer {i} is not a label: {label!r}')
        new.append((router.sentence(observation), label))
    teach_seconds = time.perf_counter() - started
    if not new:
        raise ValueError('the teacher skipped every observation; nothing to learn')
    old = router.decider
    actions = dict(getattr(old, 'actions', None) or {})  # keep the old descriptions; new labels get a plain one
    examples = base + new
    for _, label in examples:
        actions.setdefault(label, f'State {label}.')
    if len(actions) > 8:
        raise ValueError(f'a decider handles at most 8 labels; relearning would need {len(actions)}: {sorted(actions)}')
    preset = getattr(old, 'preset', None) or {}
    if trainer is None:
        from .train import fit as trainer
    started = time.perf_counter()
    decider = trainer(examples, actions, goal=preset.get('goal', ''), out=str(out), steps=steps, seed=seed,
                      name=Path(str(out)).name, quiet=quiet)
    train_seconds = time.perf_counter() - started
    if skills is not None:
        candidate = SkillTable(router.skills.items()).update(skills)   # raises before anything changes
    with router._lock:                                              # model and skills change together
        router.swap(decider)
        if skills is not None:
            router.skills._skills = dict(candidate.items())                # same table object, new contents
    if monitor is not None:
        monitor.reset()
    report = RelearnReport(at=datetime.now(timezone.utc).isoformat(timespec='seconds'), trigger=trigger,
                           teacher_calls=len(observations), teacher_skipped=skipped, new_examples=len(new),
                           examples=len(examples), labels=tuple(sorted(actions)), teach_seconds=round(teach_seconds, 3),
                           train_seconds=round(train_seconds, 3), old_sha256=getattr(old, 'sha256', ''),
                           new_sha256=getattr(decider, 'sha256', ''), out=str(out))
    if log is not None:
        with open(log, 'a', encoding='utf8') as stream:
            stream.write(json.dumps(report.to_dict(), ensure_ascii=False) + '\n')
    return report
