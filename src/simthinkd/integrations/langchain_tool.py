"""LangChain / LangGraph tool: route a step to a 2 ms decider instead of a model call.

    pip install "simthinkd[langchain]"
    from simthinkd.integrations.langchain_tool import simthinkd_tool
    tool = simthinkd_tool("doom-defend")
    tool.invoke({"state": "seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25"})
"""
from ..core import Decider


def simthinkd_tool(decider='doom-defend', name=None, description=None):
    """A LangChain StructuredTool around one decider. Input: {"state": str}. Output: {"choice", "confidence", "ms"}."""
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as error:
        raise ImportError('the LangChain tool needs: pip install "simthinkd[langchain]"') from error
    d = decider if isinstance(decider, Decider) else Decider(decider)
    actions = ', '.join(d.actions)

    def run(state: str) -> dict:
        r = d.decide(state)
        return {'choice': r.choice, 'confidence': round(r.confidence, 4), 'ms': round(r.ms, 3)}

    return StructuredTool.from_function(
        run, name=name or f'simthinkd_{d.preset["name"].replace("-", "_")}',
        description=description or (f'Pick one action ({actions}) for a short situation sentence in about 2 ms. '
                                     f'Goal: {d.preset.get("goal", "")}'))
