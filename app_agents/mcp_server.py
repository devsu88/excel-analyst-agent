"""
MCP stdio server exposing execute_python_code and search_web tools (FastMCP)
"""

from fastmcp import FastMCP


mcp = FastMCP("excel-tools")

# Lazy singletons per evitare import pesanti in startup
_python_tool = None
_web_tool = None


@mcp.tool
def execute_python_code(code: str, file_path: str) -> str:
    """Execute Python code and return results as JSON string to avoid MCP serialization issues"""
    import json
    global _python_tool
    if _python_tool is None:
        from app_agents.tools.python_tool import PythonSandboxTool
        _python_tool = PythonSandboxTool(timeout=30)
    result = _python_tool.execute(code=code, file_path=file_path)
    # Return JSON string
    return json.dumps(result, ensure_ascii=False)


@mcp.tool
def search_web(query: str) -> str:
    global _web_tool
    if _web_tool is None:
        from app_agents.tools.web_search_tool import WebSearchTool
        _web_tool = WebSearchTool(max_results=5)
    res = _web_tool.search(query)
    if res.get("success"):
        return _web_tool.format_results(res["results"])
    return f"Search failed: {res.get('error', 'Unknown error')}"


if __name__ == "__main__":
    # stdio è il default; lo specifichiamo esplicitamente per chiarezza
    mcp.run(transport="stdio")


