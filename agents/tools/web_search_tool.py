"""
Web Search Tool using DuckDuckGo
Provides web search capability for finding documentation and examples
"""

import logging
from typing import Dict, Any, List
from ddgs import DDGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSearchTool:
    """
    Web search tool using DuckDuckGo API
    """
    
    def __init__(self, max_results: int = 5):
        """
        Initialize the web search tool
        
        Args:
            max_results: Maximum number of search results to return (default: 5)
        """
        self.max_results = max_results
    
    def search(self, query: str) -> Dict[str, Any]:
        """
        Search the web using DuckDuckGo
        
        Args:
            query: Search query string
            
        Returns:
            Dictionary containing:
                - success: bool
                - results: list of search results
                - error: str (if any)
        """
        result = {
            'success': False,
            'results': [],
            'error': ''
        }
        
        try:
            logger.info(f"Searching for: {query}")
            
            with DDGS() as ddgs:
                search_results = list(ddgs.text(
                    query,
                    max_results=self.max_results
                ))
            
            # Format results
            formatted_results = []
            for idx, res in enumerate(search_results, 1):
                formatted_results.append({
                    'position': idx,
                    'title': res.get('title', ''),
                    'snippet': res.get('body', ''),
                    'url': res.get('href', '')
                })
            
            result['results'] = formatted_results
            result['success'] = True
            logger.info(f"Found {len(formatted_results)} results")
            
        except Exception as e:
            result['error'] = f"Search error: {str(e)}"
            logger.error(f"Search error: {str(e)}")
        
        return result
    
    def format_results(self, search_results: List[Dict[str, Any]]) -> str:
        """
        Format search results into a readable string
        
        Args:
            search_results: List of search result dictionaries
            
        Returns:
            Formatted string of search results
        """
        if not search_results:
            return "No results found."
        
        formatted = "Search Results:\n\n"
        for res in search_results:
            formatted += f"{res['position']}. {res['title']}\n"
            formatted += f"   {res['snippet']}\n"
            formatted += f"   URL: {res['url']}\n\n"
        
        return formatted
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get the tool definition for OpenAI function calling
        
        Returns:
            Tool definition dictionary
        """
        return {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search the web using DuckDuckGo to find Python/pandas documentation, code examples, or solutions to data analysis problems. Use this when you need help with specific pandas operations, matplotlib visualizations, or data manipulation techniques.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query. Be specific and include relevant keywords like 'pandas', 'python', 'matplotlib', etc."
                        }
                    },
                    "required": ["query"]
                }
            }
        }


