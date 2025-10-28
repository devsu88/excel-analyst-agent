"""
Excel Orchestrator Agent - MCP client using Agents SDK con handoff
"""

import logging
import os
import asyncio
from typing import Dict, Any

from agents import Agent, Runner
from agents.mcp import MCPServerStdio, create_static_tool_filter
from agents.model_settings import ModelSettings

from .web_agent import create_web_search_agent


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExcelOrchestratorAgent:
    """
    Main agent that orchestrates Excel/CSV data analysis using MCP tool execute_python_code.
    Usa handoff nativo dell'Agents SDK per delegare al WebSearchAgent quando necessario.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        # Imposta esplicitamente la chiave per l'Agents SDK
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        self.model = model

        self.system_prompt = """You are an expert Excel Data Analyst Agent specialized in analyzing and visualizing data from Excel and CSV files.

IMPORTANT: You MUST use the MCP tool execute_python_code(code, file_path) to run Python code. Do NOT just explain the code — EXECUTE it via the tool.

CRITICAL RULE: After receiving help from WebSearchAgent, you MUST immediately execute the corrected code. Never end your turn without calling execute_python_code after a handoff return.

Your capabilities:
1. Read and analyze Excel (.xlsx) and CSV files using pandas
2. Perform data manipulation, aggregation, and statistical analysis
3. Create visualizations using matplotlib and seaborn
4. Generate clear, actionable insights from data
5. Write clean, efficient Python code

Available Actions:
- execute_python_code(code, file_path): Execute Python for data analysis. The file path is provided in user messages.
- transfer to WebSearchAgent: If you encounter repeated errors or need documentation, transfer to WebSearchAgent for help.

Guidelines:
- YOU MUST CALL execute_python_code — never just describe code
- Always read the file first using: pd.read_excel(file_path) or pd.read_csv(file_path)
- Store the main dataframe in a variable named 'df' (or 'result')
- CRITICAL: Always use print() to display results and data to the user
- For dataframes: use print(df.head(10)) or print(df)
- For statistics: use print(df.describe()) or print(<metric>)
- Create clear, well-labeled visualizations; do not call plt.show() (figures are captured automatically)

CRITICAL - When to TRANSFER to WebSearchAgent:
- If the SAME error occurs 2+ times in a row
- If you get errors about missing Python builtins (Exception, ValueError, etc.)
- If you're unsure about pandas/matplotlib syntax
- To search for working code examples

DO NOT retry the same failing code more than twice. After 2 failures, TRANSFER to WebSearchAgent immediately.

CRITICAL - After WebSearchAgent returns control to you:
1. Study the documentation/examples provided by WebSearchAgent
2. Write NEW corrected Python code based on the information received
3. IMMEDIATELY EXECUTE the code using execute_python_code(code, file_path)
4. DO NOT just summarize or explain - you MUST call execute_python_code

Code Examples:

Example 1: Show first N rows
```python
import pandas as pd

df = pd.read_excel(file_path)
print("First 10 rows:")
print(df.head(10))
```

Example 2: Calculate statistics (average of a column)
```python
import pandas as pd

df = pd.read_excel(file_path)
average_sales = df['Sales'].mean()
print(f"Average Sales: {average_sales:.2f}")

avg_by_category = df.groupby('Category')['Sales'].mean()
print("\nAverage Sales by Category:")
print(avg_by_category)
```

Example 3: Create a visualization
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_excel(file_path)
country_counts = df['Country'].value_counts()
plt.figure(figsize=(10, 8))
plt.pie(country_counts, labels=country_counts.index, autopct='%1.1f%%', startangle=90)
plt.title('Distribution by Country')
plt.axis('equal')
# Do not call plt.show()
```
"""

    def analyze(self, user_query: str, file_path: str) -> Dict[str, Any]:
        try:
            # Crea due server MCP separati con filtri diversi
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

            user_msg = (
                f"Analyze this request:\n{user_query}\n\n"
                f"The file is located at: {file_path}\n\n"
                "Write Python code and call execute_python_code with that code and the same file_path."
            )

            async def _arun(msg: str):
                await python_server.connect()
                await web_server.connect()
                try:
                    # Crea il WebSearchAgent come handoff target
                    web_agent = create_web_search_agent(mcp_server=web_server, model=self.model)
                    
                    # Crea l'orchestratore con handoff al WebSearchAgent
                    orchestrator = Agent(
                        name="ExcelOrchestrator",
                        instructions=self.system_prompt,
                        mcp_servers=[python_server],
                        handoffs=[web_agent],  # Abilita handoff al WebSearchAgent
                        model=self.model,
                        # NON usare tool_choice="required" - impedisce handoff!
                        # L'agente deve essere libero di scegliere tra tool e handoff
                    )
                    
                    # Esegui con l'orchestratore come agente iniziale
                    # Aumenta max_turns per permettere handoff e retry
                    return await Runner.run(orchestrator, msg, max_turns=20)
                finally:
                    # Chiudi entrambi i server
                    for server in [python_server, web_server]:
                        close_fn = getattr(server, "close", None) or getattr(server, "aclose", None)
                        if close_fn:
                            res = close_fn()
                            if hasattr(res, "__await__"):
                                await res

            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(_arun(user_msg))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

            logger.info(f"Result from agent: {result.final_output}")
            
            final_text = result.final_output or ""

            # Estrai dataframe e images dai new_items (ToolCallOutputItem)
            # Con handoff, l'agente gestisce autonomamente il retry via WebSearchAgent
            extracted_df = None
            extracted_images = []
            import json
            
            for item in result.new_items:
                # Cerca il ToolCallOutputItem che contiene l'output del tool execute_python_code
                if hasattr(item, 'output') and isinstance(item.output, str):
                    try:
                        # L'output è una stringa JSON: {"result": "{...}"}
                        outer_json = json.loads(item.output)
                        if "result" in outer_json:
                            # Il "result" è a sua volta una stringa JSON
                            inner_json = json.loads(outer_json["result"])
                            logger.info(f"Parsed inner tool result: {inner_json}")
                            
                            if isinstance(inner_json.get("dataframe"), list):
                                extracted_df = inner_json.get("dataframe")
                            if isinstance(inner_json.get("images"), list):
                                extracted_images = inner_json.get("images")
                            # Non uscire subito - potrebbero esserci più chiamate a execute_python_code
                    except Exception as e:
                        logger.warning(f"Failed to parse tool output from item: {e}")
            
            
            logger.info(f"Final text: {final_text}")
            logger.info(f"Extracted dataframe: {extracted_df}")
            logger.info(f"Extracted images: {extracted_images}")

            return {
                'success': True,
                'output': final_text,
                'dataframe': extracted_df,
                'images': extracted_images,
                'code': None,
                'error': None
            }

        except Exception as e:
            err = f"Orchestrator error: {e}"
            logger.error(err)
            return {
                'success': False,
                'output': None,
                'dataframe': None,
                'images': [],
                'code': None,
                'error': err
            }


