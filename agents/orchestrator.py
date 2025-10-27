"""
Excel Orchestrator Agent
Main agent for Excel data analysis and visualization
"""

import logging
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from .tools.python_tool import PythonSandboxTool
from .web_agent import WebSearchAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExcelOrchestratorAgent:
    """
    Main agent that orchestrates Excel data analysis
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        """
        Initialize the Excel Orchestrator Agent
        
        Args:
            api_key: OpenAI API key
            model: OpenAI model to use (default: gpt-4o-mini)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.python_tool = PythonSandboxTool(timeout=30)
        self.web_agent = WebSearchAgent(api_key=api_key, model=model)
        
        self.system_prompt = """You are an expert Excel Data Analyst Agent specialized in analyzing and visualizing data from Excel and CSV files.

**IMPORTANT**: You MUST use the execute_python_code tool to run Python code. Do NOT just explain the code - EXECUTE IT using the tool.

Your capabilities:
1. Read and analyze Excel (.xlsx) and CSV files using pandas
2. Perform data manipulation, aggregation, and statistical analysis
3. Create visualizations using matplotlib and seaborn
4. Generate clear, actionable insights from data
5. Write clean, efficient Python code
6. Search the web for help when needed (using search_web tool)

Available Tools:
- **execute_python_code**: Execute Python code for data analysis (REQUIRED for every analysis)
- **search_web**: Search for pandas/matplotlib documentation, examples, or solutions when uncertain

Guidelines:
- **YOU MUST CALL execute_python_code TOOL** - Never just describe code, always execute it
- Always read the file first using: pd.read_excel(file_path) or pd.read_csv(file_path)
- Store the main dataframe in a variable called 'df'
- **CRITICAL**: Always use print() to display results and data to the user
- For dataframes: Use print(df.head(10)) or print(df) to show data
- For statistics: Use print(df.describe()) to show summary
- For any result: Always print() it, never just return the value
- Create clear, well-labeled visualizations
- Handle errors gracefully and provide helpful error messages
- **When uncertain about a pandas/matplotlib operation**: Use search_web tool to find documentation or examples
- **When code execution fails**: Consider using search_web to find the solution before retrying
- Always respond in clear, professional English

When to use search_web:
- You don't know how to perform a specific pandas operation
- You need examples of complex matplotlib visualizations
- The code failed and you need to find the correct syntax
- User asks for advanced statistical analysis you're unsure about

Code Examples:

**Example 1: Show first N rows**
```python
import pandas as pd

df = pd.read_excel(file_path)
print("First 10 rows:")
print(df.head(10))
```

**Example 2: Calculate statistics (e.g., average of a column)**
```python
import pandas as pd

df = pd.read_excel(file_path)
average_sales = df['Sales'].mean()
print(f"Average Sales: {average_sales:.2f}")

# Or for grouped statistics:
avg_by_category = df.groupby('Category')['Sales'].mean()
print("\nAverage Sales by Category:")
print(avg_by_category)
```

**Example 3: Create a visualization**
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_excel(file_path)

# Count values for pie chart
country_counts = df['Country'].value_counts()

# Create pie chart
plt.figure(figsize=(10, 8))
plt.pie(country_counts, labels=country_counts.index, autopct='%1.1f%%', startangle=90)
plt.title('Distribution by Country')
plt.axis('equal')
# DO NOT use plt.show() - figures are captured automatically
```

**IMPORTANT**: 
- Never use plt.show() - visualizations are captured automatically
- Always use print() to display text results and dataframes
- The file path is available as 'file_path' variable
"""
    
    def analyze(self, user_query: str, file_path: str) -> Dict[str, Any]:
        """
        Analyze Excel/CSV file based on user query
        
        Args:
            user_query: User's natural language query
            file_path: Path to the uploaded Excel/CSV file
            
        Returns:
            Dictionary containing analysis results
        """
        try:
            logger.info(f"Orchestrator processing query: {user_query}")
            logger.info(f"File path: {file_path}")
            
            # Create messages
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Analyze this request: {user_query}\n\nThe file is located at: {file_path}\n\nUSE the execute_python_code tool to run Python code that fulfills this request. Do NOT just describe the code - EXECUTE IT."}
            ]
            
            # Get tool definitions (both python execution and web search)
            tools = [
                self.python_tool.get_tool_definition(),
                self._get_web_search_tool_definition()
            ]
            
            max_iterations = 5
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Iteration {iteration}/{max_iterations}")
                
                # Call OpenAI API
                # Force tool use on first iteration to ensure code execution
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="required" if iteration == 1 else "auto"
                )
                
                response_message = response.choices[0].message
                messages.append(response_message)
                
                # Check if agent wants to use tools
                if response_message.tool_calls:
                    for tool_call in response_message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)
                        
                        logger.info(f"Agent calling tool: {function_name}")
                        
                        if function_name == "execute_python_code":
                            code = function_args.get("code", "")
                            logger.info(f"Executing code:\n{code}")
                            
                            # Execute the code
                            execution_result = self.python_tool.execute(
                                code=code,
                                file_path=file_path
                            )
                            
                            # Format result for the agent
                            if execution_result['success']:
                                result_msg = f"Code executed successfully.\n\nOutput:\n{execution_result['output']}"
                                if execution_result['dataframe']:
                                    result_msg += f"\n\nDataFrame preview: {len(execution_result['dataframe'])} rows returned"
                                if execution_result['images']:
                                    result_msg += f"\n\n{len(execution_result['images'])} visualization(s) created"
                            else:
                                result_msg = f"Code execution failed.\n\nError:\n{execution_result['error']}"
                                result_msg += "\n\nConsider using search_web tool to find the solution or correct syntax."
                            
                            # Add tool response to messages
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result_msg
                            })
                            
                            # If successful, return the results
                            if execution_result['success']:
                                return {
                                    'success': True,
                                    'output': execution_result['output'],
                                    'dataframe': execution_result['dataframe'],
                                    'images': execution_result['images'],
                                    'code': code,
                                    'error': None
                                }
                        
                        elif function_name == "search_web":
                            search_query = function_args.get("query", "")
                            logger.info(f"Searching web for: {search_query}")
                            
                            # Execute web search
                            search_result = self._execute_web_search(search_query)
                            
                            # Add search results to messages
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": f"Search results:\n\n{search_result}"
                            })
                    
                    # Continue the conversation loop
                    continue
                
                else:
                    # Agent provided a final response without tool calls
                    final_response = response_message.content
                    logger.info("Agent provided final response")
                    
                    return {
                        'success': True,
                        'output': final_response,
                        'dataframe': None,
                        'images': [],
                        'code': None,
                        'error': None
                    }
            
            # Max iterations reached
            logger.warning("Max iterations reached")
            return {
                'success': False,
                'output': None,
                'dataframe': None,
                'images': [],
                'code': None,
                'error': "Maximum iterations reached. Please try rephrasing your query."
            }
            
        except Exception as e:
            error_msg = f"Orchestrator error: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'output': None,
                'dataframe': None,
                'images': [],
                'code': None,
                'error': error_msg
            }
    
    def _get_web_search_tool_definition(self) -> Dict[str, Any]:
        """
        Get the tool definition for web search
        
        Returns:
            Tool definition dictionary for OpenAI function calling
        """
        return {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search the web for Python/pandas/matplotlib documentation, code examples, or solutions to data analysis problems. Use this when you're uncertain about how to implement something or when code execution fails and you need help.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for finding Python/pandas/matplotlib help. Be specific and include keywords like 'pandas', 'matplotlib', 'how to', etc. Example: 'pandas groupby multiple columns example' or 'matplotlib pie chart with percentages'"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    
    def _execute_web_search(self, query: str) -> str:
        """
        Execute a web search using the WebSearch Agent
        
        Args:
            query: Search query
            
        Returns:
            Formatted search results as string
        """
        logger.info(f"Executing web search: {query}")
        result = self.web_agent.ask(query)
        return result if result else "No results found or search failed."


