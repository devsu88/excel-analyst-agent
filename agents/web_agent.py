"""
WebSearch Agent
Support agent for finding documentation and code examples
"""

import logging
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from .tools.web_search_tool import WebSearchTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSearchAgent:
    """
    Agent specialized in web search for Python/pandas documentation
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        """
        Initialize the WebSearch Agent
        
        Args:
            api_key: OpenAI API key
            model: OpenAI model to use (default: gpt-4o-mini)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.search_tool = WebSearchTool(max_results=5)
        
        self.system_prompt = """You are a research assistant specialized in finding Python, pandas, and data analysis documentation and examples.

Your role:
1. Search the web for relevant documentation, tutorials, and code examples
2. Summarize findings concisely and actionably
3. Provide specific code snippets when available
4. Focus on pandas, numpy, matplotlib, and seaborn libraries
5. Always respond in clear, professional English

When searching:
- Use specific technical terms
- Focus on official documentation and reputable sources
- Prioritize recent and accurate information
- Extract the most relevant code examples

Format your responses clearly with:
- Brief explanation of the solution
- Relevant code examples
- Key points to remember
"""
    
    def search(self, query: str) -> Dict[str, Any]:
        """
        Process a search query and return summarized results
        
        Args:
            query: User's search query
            
        Returns:
            Dictionary containing the response and metadata
        """
        try:
            logger.info(f"WebSearch Agent processing query: {query}")
            
            # Create messages for the agent
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Search for information about: {query}"}
            ]
            
            # Get tool definition
            tools = [self.search_tool.get_tool_definition()]
            
            # First API call - agent decides to use tool
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            messages.append(response_message)
            
            # Check if agent wants to use the search tool
            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    if tool_call.function.name == "search_web":
                        # Execute the search
                        function_args = json.loads(tool_call.function.arguments)
                        search_query = function_args.get("query", query)
                        
                        logger.info(f"Executing web search: {search_query}")
                        search_result = self.search_tool.search(search_query)
                        
                        # Format the search results
                        if search_result['success']:
                            formatted_results = self.search_tool.format_results(
                                search_result['results']
                            )
                        else:
                            formatted_results = f"Search failed: {search_result['error']}"
                        
                        # Add tool response to messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": formatted_results
                        })
                
                # Second API call - agent summarizes the results
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages
                )
                
                final_content = final_response.choices[0].message.content
                
            else:
                # Agent responded without using tools
                final_content = response_message.content
            
            logger.info("WebSearch Agent completed successfully")
            
            return {
                'success': True,
                'response': final_content,
                'error': None
            }
            
        except Exception as e:
            error_msg = f"WebSearch Agent error: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'response': None,
                'error': error_msg
            }
    
    def ask(self, question: str) -> Optional[str]:
        """
        Convenience method to ask a question and get the response
        
        Args:
            question: Question to ask the agent
            
        Returns:
            Response string or None if error
        """
        result = self.search(question)
        return result['response'] if result['success'] else None


