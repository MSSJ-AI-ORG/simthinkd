"""SimThink D: a small decision model that picks one action in about 2 ms on one CPU core.

    from simthinkd import Decider
    print(Decider("doom-defend").decide("seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25"))
"""
from .core import Decider, Decision, available, build_request
from .score import Score, Scorer

__version__ = '0.2.0'
__all__ = ['Decider', 'Decision', 'Score', 'Scorer', 'available', 'build_request', 'fit', 'fit_score', '__version__']


def fit(*args, **kwargs):
    """Train a decider from (situation, action) pairs. See simthinkd.train.fit. Needs simthinkd[train]."""
    from .train import fit as _fit
    return _fit(*args, **kwargs)


def fit_score(*args, **kwargs):
    """Train a score model from (situation, number) pairs. See simthinkd.score.fit_score. Needs simthinkd[train]."""
    from .score import fit_score as _fit_score
    return _fit_score(*args, **kwargs)
