"""
NL2SQL Agent - TODO: Implementează nodurile
"""
import json
import logging
import re
from pathlib import Path
from typing import Literal

import pandas as pd
import sqlparse
from langgraph.graph import StateGraph, END
from skillab import get_llm
from skillab.llm.base import LLMProvider
from skillab.prompts import PromptRegistry

from state import NL2SQLState

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Operații SQL interzise (agentul e read-only — doar SELECT).
FORBIDDEN_SQL = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "GRANT", "CREATE"]

def _clean_sql(text: str) -> str:
    """Curăță SQL-ul întors de LLM: scoate fences ```sql ... ``` și ';' final."""
    match = re.search(r"```(?:sql)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    sql = match.group(1) if match else text
    return sql.strip().rstrip(";").strip()


class NL2SQLAgent:
    """
    Flow:
        get_context → generate_sql → validate → execute
                                        ↓
                                    handle_error
    """

    def __init__(
        self,
        table_name: str,
        schema_path: str,
        db_url: str = "postgresql://demo:demo123@localhost:5433/rag_demo",
        max_retries: int = 2,
        llm: LLMProvider | None = None,
    ):
        self.table_name = table_name
        self.db_url = db_url
        self.max_retries = max_retries
        self.llm = llm or get_llm()
        self.prompts = PromptRegistry(str(PROMPTS_DIR))

        # Load schema
        self.schema = json.loads(Path(schema_path).read_text())

        self.graph = self._build_graph()

    # === NODES ===

    def node_get_context(self, state: NL2SQLState) -> dict:
        """COMPLET."""
        return {
            "schema_context": self.schema,
            "table_name": self.table_name,
        }

    def node_generate_sql(self, state: NL2SQLState) -> dict:
        """
        TODO: Generează SQL.

        1. Renderează prompt "nl2sql_generate"
        2. Apelează LLM
        3. Curăță răspunsul (remove ```sql blocks)
        4. Return {"sql_query": ...}
        """
        logger.info(f"[GENERATE] {state.question}")

        # TODO: implementează

        # Pe retry, SQL-ul a fost deja corectat în handle_error (cu contextul erorii).
        # Nu-l regenerăm de la zero — altfel am pierde corectura, pentru că graful
        # rutează handle_error → generate_sql.
        if state.retry_count > 0 and state.sql_query:
            logger.info("[GENERATE] retry: folosesc SQL-ul corectat din handle_error")
            return {"sql_query": state.sql_query}

        schema = state.schema_context
        prompt = self.prompts.render(
            "nl2sql_generate",
            table_name=state.table_name,
            table_description=schema.get("description", ""),
            columns=schema.get("columns", {}),
            business_rules=schema.get("business_rules", {}),
            question=state.question,
        )

        response = self.llm.generate_sync([{"role": "user", "content": prompt}])
        sql = _clean_sql(response)
        logger.info(f"[GENERATE] SQL: {sql}")
        return {"sql_query": sql}

    def node_validate_sql(self, state: NL2SQLState) -> dict:
        """
        TODO: Validează SQL.

        1. Check pentru SQL injection patterns
        2. Parsează cu sqlparse
        3. Verifică că e SELECT
        4. Return {"is_valid": bool, "validation_error": str}
        """
        sql = state.sql_query
        logger.info(f"[VALIDATE] {sql[:50]}...")

        # TODO: implementează

         # 1. Blocăm operațiile periculoase (agent read-only).
        upper = sql.upper()
        for kw in FORBIDDEN_SQL:
            if re.search(rf"\b{kw}\b", upper):
                return {"is_valid": False, "validation_error": f"Operație interzisă: {kw}"}

        # 2. Interzicem statement-uri multiple (clasic SQL injection via ';').
        if ";" in sql:
            return {"is_valid": False, "validation_error": "Statement-uri multiple nu sunt permise"}

        # 3. Parsăm cu sqlparse și verificăm că e un SELECT.
        parsed = sqlparse.parse(sql)
        if not parsed:
            return {"is_valid": False, "validation_error": "SQL gol sau neparsabil"}
        stmt_type = parsed[0].get_type()
        if stmt_type != "SELECT":
            return {"is_valid": False, "validation_error": f"Doar SELECT permis, am primit '{stmt_type}'"}

        return {"is_valid": True, "validation_error": ""}

    def node_execute_sql(self, state: NL2SQLState) -> dict:
        """
        TODO: Execută SQL.

        1. Folosește transaction() + session.execute(text(sql))
        2. Convertește la DataFrame: df = pd.DataFrame(result.mappings().all())
        3. Return {"result": df, "status": "success"} sau {"execution_error": ...}
        """
        logger.info("[EXECUTE]")

        # TODO: implementează

        from database import transaction
        from sqlalchemy import text

        try:
            with transaction() as session:
                result = session.execute(text(state.sql_query))
                df = pd.DataFrame(result.mappings().all())
        except Exception as e:
            # Eroare la execuție → o salvăm; routing-ul va merge la handle_error.
            logger.warning(f"[EXECUTE] eroare: {e}")
            return {"execution_error": str(e)}

        # Succes → golim orice eroare anterioară (de la un retry) ca să rutăm spre END.
        logger.info(f"[EXECUTE] OK, {len(df)} rânduri")
        return {"result": df, "execution_error": "", "status": "success"}

    def node_handle_error(self, state: NL2SQLState) -> dict:
        """
        TODO: Handle error + retry.

        1. Increment retry_count
        2. Dacă >= max_retries: return {"status": "failed"}
        3. Renderează prompt "nl2sql_error"
        4. Apelează LLM pentru SQL corectat
        5. Return {"sql_query": new_sql, "retry_count": ...}
        """
        logger.info("[ERROR]")

        # TODO: implementează

        new_retry = state.retry_count + 1

        # Am epuizat încercările → renunțăm (routing-ul merge la END).
        # >= max_retries ca să ne aliniem cu _route_after_error.
        if new_retry >= state.max_retries:
            logger.info(f"[ERROR] max_retries ({state.max_retries}) atins; renunț")
            return {"retry_count": new_retry, "status": "failed"}

        # Mai avem încercări → cerem LLM-ului SQL-ul corectat, cu eroarea ca context.
        schema = state.schema_context
        error_msg = state.execution_error or state.validation_error
        prompt = self.prompts.render(
            "nl2sql_error",
            table_name=state.table_name,
            question=state.question,
            failed_sql=state.sql_query,
            error_message=error_msg,
            columns=schema.get("columns", {}),
        )

        response = self.llm.generate_sync([{"role": "user", "content": prompt}])
        corrected = _clean_sql(response)
        logger.info(f"[ERROR] SQL corectat: {corrected}")

        # Punem SQL-ul corectat și golim erorile; generate_sql îl va prelua ca atare.
        return {
            "sql_query": corrected,
            "retry_count": new_retry,
            "execution_error": "",
            "validation_error": "",
        }

    # === ROUTING ===

    def _route_after_validate(self, state: NL2SQLState) -> str:
        return "execute_sql" if state.is_valid else "handle_error"

    def _route_after_execute(self, state: NL2SQLState) -> str:
        return END if not state.execution_error else "handle_error"

    def _route_after_error(self, state: NL2SQLState) -> str:
        return "generate_sql" if state.retry_count < self.max_retries else END

    # === GRAPH ===

    def _build_graph(self):
        graph = StateGraph(NL2SQLState)

        graph.add_node("get_context", self.node_get_context)
        graph.add_node("generate_sql", self.node_generate_sql)
        graph.add_node("validate_sql", self.node_validate_sql)
        graph.add_node("execute_sql", self.node_execute_sql)
        graph.add_node("handle_error", self.node_handle_error)

        graph.set_entry_point("get_context")
        graph.add_edge("get_context", "generate_sql")
        graph.add_edge("generate_sql", "validate_sql")
        graph.add_conditional_edges("validate_sql", self._route_after_validate, ["execute_sql", "handle_error"])
        graph.add_conditional_edges("execute_sql", self._route_after_execute, [END, "handle_error"])
        graph.add_conditional_edges("handle_error", self._route_after_error, ["generate_sql", END])

        return graph.compile()

    def run(self, question: str) -> NL2SQLState:
        """Execută agentul."""
        initial = NL2SQLState(
            question=question,
            table_name=self.table_name,
            max_retries=self.max_retries,
        )
        final = self.graph.invoke(initial)
        return NL2SQLState(**final)
