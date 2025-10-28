"""
WebSearch Agent - MCP client using Agents SDK
"""

import logging
import os
from typing import Optional

from agents import Agent
from agents.mcp import MCPServerStdio, create_static_tool_filter
from agents.model_settings import ModelSettings


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# System prompt per il WebSearchAgent (usato come handoff target)
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

IMPORTANT: After providing the information, return control to the calling agent.
Remind the calling agent to EXECUTE the code immediately using execute_python_code."""


def create_web_search_agent(mcp_server: MCPServerStdio, model: str = "gpt-4o-mini") -> Agent:
    """
    Crea un Agent SDK per web search da usare come handoff target
    
    Args:
        mcp_server: Server MCP già configurato con filtro tool search_web
        model: Modello OpenAI da usare
    
    Returns:
        Agent configurato per web search
    """
    return Agent(
        name="WebSearchAgent",
        instructions=WEB_SEARCH_INSTRUCTIONS,
        mcp_servers=[mcp_server],
        model=model,
        model_settings=ModelSettings(tool_choice="required"),
    )


# Backward compatibility: mantieni la classe wrapper per chiamate legacy
class WebSearchAgent:
    """
    Wrapper class per compatibilità con codice esistente.
    Per handoff, usa create_web_search_agent() direttamente.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        self.model = model
        self.system_prompt = WEB_SEARCH_INSTRUCTIONS

    def ask(self, question: str) -> Optional[str]:
        try:
            server = MCPServerStdio(
                name="excel-tools",
                params={"command": "python", "args": ["-m", "app_agents.mcp_server"]},
                cache_tools_list=True,
                tool_filter=create_static_tool_filter(allowed_tool_names=["search_web"]),
            )

            async def _arun(msg: str):
                await server.connect()
                try:
                    agent = Agent(
                        name="WebSearchAgent",
                        instructions=self.system_prompt,
                        mcp_servers=[server],
                        model_settings=ModelSettings(tool_choice="required"),
                    )
                    return await Runner.run(agent, msg)
                finally:
                    close_fn = getattr(server, "close", None) or getattr(server, "aclose", None)
                    if close_fn:
                        res = close_fn()
                        if hasattr(res, "__await__"):
                            await res

            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(_arun(f"Search for: {question}"))
            finally:
                loop.close()
                asyncio.set_event_loop(None)
            return result.final_output
        except Exception as e:
            logger.error(f"WebSearch Agent error: {e}")
            return None

    # Compatibility with legacy interface
    def search(self, query: str) -> dict:
        content = self.ask(query)
        return {'success': content is not None, 'response': content, 'error': None if content else 'search failed'}


