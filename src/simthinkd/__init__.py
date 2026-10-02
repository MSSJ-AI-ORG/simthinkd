"""SimThink D: a small decision model that picks one action in about 2 ms on one CPU core.

    from simthinkd import Decider
    print(Decider("doom-defend").decide("seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25"))
"""
from .core import Decider, Decision, available, build_request

__version__ = '0.1.0'
__all__ = ['Decider', 'Decision', 'available', 'build_request', 'fit', '__version__']


def fit(*args, **kwargs):
    """Train a decider from (situation, action) pairs. See simthinkd.train.fit. Needs simthinkd[train]."""
    from .train import fit as _fit
    return _fit(*args, **kwargs)
