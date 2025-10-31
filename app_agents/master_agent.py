"""
Master Agent - coordina ExcelAnalysisAgent e WebSearchAgent come strumenti
"""

import logging
import os
import asyncio
from typing import Dict, Any, Optional

from agents import Agent, Runner
from agents.mcp import MCPServerStdio, create_static_tool_filter
from agents.model_settings import ModelSettings

from .excel_agent import ExcelAnalysisAgent
from .web_agent import create_web_search_agent


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MasterAgent:
    """
    Agente master che coordina:
    - ExcelAnalysisAgent: esecuzione di codice Python tramite MCP execute_python_code
    - WebSearchAgent: ricerca documentazione tramite MCP search_web

    Strategia:
    1) Prova l'analisi con l'ExcelAnalysisAgent
    2) Se fallisce o l'output è insufficiente, interroga il WebSearchAgent
    3) Ritenta l'analisi Excel con il contesto ottenuto dal web
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        self.model = model

    def _run_web_search(self, query: str) -> Optional[str]:
        """
        Esegue il WebSearchAgent come tool e ritorna il testo trovato
        """
        async def _arun(msg: str) -> Any:
            server = MCPServerStdio(
                name="excel-tools-web",
                params={"command": "python", "args": ["-m", "app_agents.mcp_server"]},
                cache_tools_list=True,
                tool_filter=create_static_tool_filter(allowed_tool_names=["search_web"]),
            )
            await server.connect()
            try:
                web_agent = create_web_search_agent(mcp_server=server, model=self.model)
                result = await Runner.run(web_agent, msg)
                return result
            finally:
                close_fn = getattr(server, "close", None) or getattr(server, "aclose", None)
                if close_fn:
                    res = close_fn()
                    if hasattr(res, "__await__"):
                        await res

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_arun(f"Search for help about: {query}"))
        finally:
            loop.close()
            asyncio.set_event_loop(None)
        return getattr(result, "final_output", None)

    def analyze(self, user_query: str, file_path: str) -> Dict[str, Any]:
        """
        Coordina i due agenti per ottenere il miglior risultato possibile
        """
        try:
            excel = ExcelAnalysisAgent(api_key=os.environ.get("OPENAI_API_KEY", ""), model=self.model)

            # Primo tentativo: direttamente con l'agente Excel
            logger.info("MasterAgent: Primo tentativo con ExcelAnalysisAgent")
            first_result = excel.analyze(user_query=user_query, file_path=file_path)
            if first_result.get("success") and (
                (first_result.get("output") and first_result["output"].strip())
                or first_result.get("dataframe")
                or (first_result.get("images") and len(first_result["images"]) > 0)
            ):
                return first_result

            # Se fallisce, raccogli contesto dal WebSearchAgent
            logger.info("MasterAgent: Primo tentativo insufficiente, avvio WebSearchAgent per contesto")
            web_context = self._run_web_search(
                f"User query: {user_query}. If available, include pandas/matplotlib guidance."
            ) or ""

            # Secondo tentativo: arricchisci la richiesta per l'agente Excel
            augmented_query = (
                f"{user_query}\n\nAdditional guidance from web research:\n{web_context}\n\n"
                "Use this guidance to write correct Python code and call execute_python_code."
            )
            logger.info("MasterAgent: Secondo tentativo con ExcelAnalysisAgent usando contesto web")
            second_result = excel.analyze(user_query=augmented_query, file_path=file_path)

            # Allegare il contesto web all'output testuale per visibilità
            if web_context:
                base_output = second_result.get("output") or ""
                combined = base_output + ("\n\n---\nWeb research context used:\n" + web_context if web_context else "")
                second_result["output"] = combined

            return second_result

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


