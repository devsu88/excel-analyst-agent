"""
Master Agent - coordinates ExcelAnalysisAgent and WebSearchAgent as tools
"""

import logging
import os
import asyncio
import json
from typing import Dict, Any, Optional

from agents import Agent, Runner
from agents.mcp import MCPServerStdio, create_static_tool_filter

from .excel_agent import create_excel_agent
from .web_agent import create_web_search_agent


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


MASTER_AGENT_PROMPT = """
You are the orchestrator of a multi-agent system. Your task is to take the user's query and the file path and pass it to the appropriate agent tool.

Available agent tools:
- excel_analysis_agent: Executes Python code for data analysis and visualization using pandas and matplotlib. 
  When calling this tool, you MUST pass the complete user query and the file path so it can execute the correct analysis.
- web_search_agent: Searches the web for documentation, examples, and solutions.

Your strategy:
1. First, try to use the excel_analysis_agent to directly answer the user's query using the file path.
   IMPORTANT: When calling excel_analysis_agent, include the FULL user query in your message to the tool.
2. If the analysis fails or needs additional context, use the web_search_agent to find relevant information.
3. Use the web search results to guide a retry with the excel_analysis_agent.

Always provide clear, actionable results to the user.
"""


class MasterAgent:
    """
    Master agent that coordinates ExcelAnalysisAgent and WebSearchAgent as tools.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        self.model = model

    def analyze(self, user_query: str, file_path: str) -> Dict[str, Any]:
        """
        Coordinate the two agents to get the best possible result
        """
        async def _arun():
            # Create MCP servers
            python_server = MCPServerStdio(
                name="excel-tools-python",
                params={"command": "python", "args": ["-m", "app_agents.mcp_server"]},
                cache_tools_list=True,
                use_structured_content=True,
                tool_filter=create_static_tool_filter(allowed_tool_names=["execute_python_code"]),
            )
            
            web_server = MCPServerStdio(
                name="excel-tools-web",
                params={"command": "python", "args": ["-m", "app_agents.mcp_server"]},
                cache_tools_list=True,
                tool_filter=create_static_tool_filter(allowed_tool_names=["search_web"]),
            )
            
            # Connect servers
            await python_server.connect()
            await web_server.connect()
            
            try:
                # Create specialized agents using functions from their respective modules
                excel_agent = create_excel_agent(mcp_server=python_server, model=self.model)
                web_agent = create_web_search_agent(mcp_server=web_server, model=self.model)
                
                # Create orchestrator agent with other agents as tools
                orchestrator = Agent(
                    name="MasterAgent",
                    model=self.model,
                    instructions=MASTER_AGENT_PROMPT,
                    tools=[
                        excel_agent.as_tool(
                            tool_name="excel_analysis_agent",
                            tool_description="Execute Python code to analyze Excel/CSV files and create visualizations. The agent receives the user query and file path and must execute the exact analysis requested."
                        ),
                        web_agent.as_tool(
                            tool_name="web_search_agent",
                            tool_description="Search the web for up-to-date information, documentation, and code examples"
                        ),
                    ],
                )
                
                # Prepare user message with file path
                user_msg = (
                    f"User query: {user_query}\n"
                    f"File path: {file_path}\n\n"
                    f"Call the excel_analysis_agent tool with this exact message:\n"
                    f"'Analyze this request: {user_query}\\n\\nThe file is located at: {file_path}\\n\\n"
                    f"Write Python code and call execute_python_code with that code and the same file_path.'\n\n"
                    f"Make sure to pass the complete user query to the excel_analysis_agent so it can perform the correct analysis."
                )
                
                # Run orchestrator
                result = await Runner.run(orchestrator, user_msg, max_turns=20)
                
                return result
            finally:
                # Clean up servers
                for server in [python_server, web_server]:
                    close_fn = getattr(server, "close", None) or getattr(server, "aclose", None)
                    if close_fn:
                        res = close_fn()
                        if hasattr(res, "__await__"):
                            await res

        try:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(_arun())
            finally:
                loop.close()
                asyncio.set_event_loop(None)

            raw_output = result.final_output or ""
            
            # Extract dataframe and images from tool output
            extracted_df = None
            extracted_images = []
            final_text = raw_output
            
            # Extract from result.new_items - Item 1 (ToolCallOutputItem) contains the JSON
            for item in result.new_items:
                if hasattr(item, 'output') and isinstance(item.output, str):
                    # Extract JSON from markdown code blocks if present
                    json_str = item.output
                    if "```json" in item.output:
                        parts = item.output.split("```json")
                        if len(parts) > 1:
                            json_str = parts[1].split("```")[0].strip()
                    
                    try:
                        tool_result = json.loads(json_str)
                        if isinstance(tool_result, dict) and "success" in tool_result:
                            # Extract dataframe and images from tool result
                            if isinstance(tool_result.get("dataframe"), list) and tool_result.get("dataframe"):
                                extracted_df = tool_result.get("dataframe")
                            if isinstance(tool_result.get("images"), list) and tool_result.get("images"):
                                extracted_images = tool_result.get("images")
                            break  # Found the JSON, no need to continue
                    except (json.JSONDecodeError, ValueError):
                        continue

            return {
                'success': True,
                'output': final_text,
                'dataframe': extracted_df,
                'images': extracted_images,
                'code': None,
                'error': None
            }

        except Exception as e:
            err = f"MasterAgent error: {e}"
            logger.error(err)
            return {
                "success": False,
                "output": None,
                "dataframe": None,
                "images": [],
                "code": None,
                "error": err,
            }


