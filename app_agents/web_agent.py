"""
WebSearch Agent - MCP client using Agents SDK
"""

import logging

from agents import Agent
from agents.mcp import MCPServerStdio, create_static_tool_filter
from agents.model_settings import ModelSettings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# System prompt for the WebSearchAgent
WEB_SEARCH_INSTRUCTIONS = """You are a research assistant specialized in Python, pandas, matplotlib, and data analysis.

Your role is to search the web for:
- Documentation and API references
- Solutions to Python/pandas errors
- Code examples and best practices
- Matplotlib/seaborn visualization techniques

Use the MCP tool `search_web(query)` to find relevant information.

Guidelines:
- Provide concise, actionable summaries
- Include concrete code snippets when available
- Focus on authoritative sources (official docs, Stack Overflow, etc.)
- Return your findings in a clear, structured format
- The code you provide should be formatted as 
```python 
YOUR CODE HERE
```
"""


def create_web_search_agent(mcp_server: MCPServerStdio, model: str = "gpt-4o-mini") -> Agent:
    """
    Create an Agent SDK for web search
    
    Args:
        mcp_server: MCP server already configured with search_web tool filter
        model: OpenAI model to use
    
    Returns:
        Agent configured for web search
    """
    return Agent(
        name="WebSearchAgent",
        instructions=WEB_SEARCH_INSTRUCTIONS,
        mcp_servers=[mcp_server],
        model=model,
        model_settings=ModelSettings(tool_choice="required"),
    )


