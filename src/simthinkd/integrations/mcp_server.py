"""MCP server: lets an agent (Claude Desktop, Cursor, any MCP client) ask a SimThink D decider for a fast decision.

    pip install "simthinkd[mcp]"
    python -m simthinkd.integrations.mcp_server            # stdio transport

Client config example:
    {"mcpServers": {"simthinkd": {"command": "python", "args": ["-m", "simthinkd.integrations.mcp_server"]}}}
"""
from functools import lru_cache

from ..core import Decider, available


@lru_cache(maxsize=8)
def _decider(name):
    return Decider(name)


def list_deciders() -> dict:
    """Bundled deciders and what each was trained for."""
    return available()


def decide(state: str, decider: str = 'doom-defend', actions: dict | None = None, goal: str | None = None) -> dict:
    """Pick one action for a short situation sentence. Returns choice, confidence, probabilities and time in ms.

    `actions` ({name: description}) and `goal` default to the ones the decider was trained with.
    """
    r = _decider(decider).decide(state, actions=actions, goal=goal)
    return {'choice': r.choice, 'confidence': r.confidence, 'probabilities': r.probabilities, 'ms': round(r.ms, 3)}


def build_server():
    try:
        from mcp.server.mcpserver import MCPServer as Server      # mcp 2.x
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP as Server      # mcp 1.x
        except ImportError as error:
            raise ImportError('the MCP server needs: pip install "simthinkd[mcp]"') from error
    server = Server('simthinkd')
    server.tool()(list_deciders)
    server.tool()(decide)
    return server


def main():
    build_server().run()


if __name__ == '__main__':
    main()
