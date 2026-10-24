try:
    from .mcp_instance import mcp
except ImportError:
    from mcp_instance import mcp

@mcp.tool()
def ping(message: str = "hello") -> str:
    """Echo back a message to confirm the CFD Copilot MCP server is
    reachable and responding. Call this first to verify the connection
    before any CFD tools are added."""
    return f"cfd-copilot server received: {message}"

try:
    from . import geometry
except ImportError:
    import geometry

try:
    from . import meshing
except ImportError:
    import meshing


try:
    from . import case_setup
except ImportError:
    import case_setup

try:
    from . import solver_run
except ImportError:
    import solver_run

try:
    from . import postprocess
except ImportError:
    import postprocess

if __name__ == "__main__":
    mcp.run()