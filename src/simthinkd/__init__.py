"""SimThink D: a small decision model that picks one action in about 2 ms on one CPU core.

    from simthinkd import Decider
    print(Decider("doom-defend").decide("seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25"))

Router kit (0.4.0): Router + SkillTable hand a case over to a large model when the decider is unsure, the state is
unknown, or the last fast action did not lead to an expected next state; relearn() retrains and hot-swaps.
DOM input: DomAdapter, CombinedAdapter, and DomVerifier + VerifiedRouter (capture decides, DOM verifies).
"""
from .adapters import PipelineAdapter, ScreenAdapter, VectorAdapter
from .dom_adapter import CombinedAdapter, DomAdapter, DomVerifier, VerifiedRouter
from .core import Decider, Decision, available, build_request
from .relearn import RelearnReport, relearn
from .router import HandoffMonitor, Route, Router, Skill, SkillTable
from .score import Score, Scorer

__version__ = '0.4.0'
__all__ = ['Decider', 'Decision', 'Score', 'Scorer', 'available', 'build_request', 'fit', 'fit_score', '__version__',
           'Router', 'Route', 'Skill', 'SkillTable', 'HandoffMonitor', 'relearn', 'RelearnReport',
           'ScreenAdapter', 'PipelineAdapter', 'VectorAdapter',
           'DomAdapter', 'CombinedAdapter', 'DomVerifier', 'VerifiedRouter']


def fit(*args, **kwargs):
    """Train a decider from (situation, action) pairs. See simthinkd.train.fit. Needs simthinkd[train]."""
    from .train import fit as _fit
    return _fit(*args, **kwargs)


def fit_score(*args, **kwargs):
    """Train a score model from (situation, number) pairs. See simthinkd.score.fit_score. Needs simthinkd[train]."""
    from .score import fit_score as _fit_score
    return _fit_score(*args, **kwargs)
