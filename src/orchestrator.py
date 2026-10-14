"""
Orchestrator - Supervizor care coordonează RAG Agent

Flow:
    call_rag → evaluate ──┬──→ answer → END
         ↑                │
         │   can_answer   │
         │   = false      │
         └────────────────┘

TODO pentru studenți: node_evaluate, node_answer
"""
import logging
import re
from pathlib import Path
from typing import Literal

from langgraph.graph import StateGraph, START, END
from skillab import get_llm
from skillab.llm.base import LLMProvider
from skillab.prompts import PromptRegistry

from state import OrchestratorState, OrchestratorFeedback
from rag_agent import RAGAgent, RAGAgentConfig

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def _extract_json(text: str) -> str:
    """Extrage blocul JSON dintr-un răspuns LLM (din ```json ... ``` sau brut)."""
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    return match.group(1) if match else text.strip()


def _build_context(results) -> str:
    """Construiește contextul text din chunk-urile găsite de RAG."""
    return "\n\n".join(f"[{r.file_name}]\n{r.content}" for r in results)

class OrchestratorConfig:
    max_iterations: int = 3
    min_score: float = 0.25


class Orchestrator:
    """
    Supervizor care coordonează RAG Agent.

    Flow:
        1. Apelează RAG Agent pentru căutare
        2. Evaluează: pot răspunde cu aceste chunks?
        3. Dacă DA → generează răspuns
        4. Dacă NU → trimite feedback la RAG Agent, repeat
    """

    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        llm: LLMProvider | None = None,
    ):
        self.config = config or OrchestratorConfig()
        self.llm = llm or get_llm()
        self.prompts = PromptRegistry(str(PROMPTS_DIR))

        # RAG Agent - graf separat
        rag_config = RAGAgentConfig()
        rag_config.default_threshold = self.config.min_score
        self.rag = RAGAgent(self.llm, rag_config)

    # === NODES ===

    def node_call_rag(self, state: OrchestratorState) -> dict:
        """Apelează RAG Agent pentru căutare. COMPLET - nu modifica."""
        logger.info(f"[CALL_RAG] iter {state.iteration + 1}")

        # Apelează RAG Agent cu query și feedback (dacă există)
        rag_result = self.rag.run(
            query=state.query,
            feedback=state.feedback,  # None prima dată
        )

        return {
            "rag_result": rag_result.result,
            "iteration": state.iteration + 1,
        }

    def node_evaluate(self, state: OrchestratorState) -> dict:
        """
        TODO: Evaluează dacă contextul RAG e suficient.

        1. Construiește context din state.rag_result.results:
           context = "\\n\\n".join(f"[{r.file_name}]\\n{r.content}" for r in results)

        2. Renderează prompt "rag_evaluate" cu:
           - query=state.query
           - context=context
           - max_score=state.rag_result.max_score
           - avg_score=state.rag_result.avg_score

        3. Apelează LLM:
           response = self.llm.generate_sync([{"role": "user", "content": prompt}])

        4. Parsează JSON în Pydantic:
           - Extrage JSON din ```json ... ```
           - feedback = OrchestratorFeedback.model_validate_json(json_str)

        5. Return {"feedback": feedback}
        """
        logger.info(f"[EVALUATE] iter {state.iteration}")

        # TODO: implementează

        results = state.rag_result.results if state.rag_result else []

        # Fără niciun chunk nu are rost să întrebăm LLM-ul: clar nu putem răspunde.
        # Întoarcem feedback negativ → routing-ul va mai încerca o căutare.
        if not results:
            return {"feedback": OrchestratorFeedback(
                can_answer=False,
                missing_info="Nu s-a găsit niciun chunk relevant.",
                suggestion="Reformulează query-ul sau scade threshold-ul.",
            )}

        # Avem context → cerem LLM-ului verdictul "pot răspunde?".
        context = _build_context(results)
        prompt = self.prompts.render(
            "rag_evaluate",
            query=state.query,
            context=context,
            max_score=state.rag_result.max_score,
            avg_score=state.rag_result.avg_score,
        )

        response = self.llm.generate_sync([{"role": "user", "content": prompt}])
        try:
            feedback = OrchestratorFeedback.model_validate_json(_extract_json(response))
        except Exception as e:
            # Dacă nu putem parsa, presupunem că nu putem răspunde (fail-safe).
            logger.warning(f"[EVALUATE] parse eșuat ({e}); presupun can_answer=False")
            feedback = OrchestratorFeedback(
                can_answer=False, missing_info="Răspuns LLM neparsabil"
            )

        logger.info(f"[EVALUATE] can_answer={feedback.can_answer}")
        return {"feedback": feedback}
    

    def node_answer(self, state: OrchestratorState) -> dict:
        """
        TODO: Generează răspunsul final.

        1. Construiește context din state.rag_result.results:
           context = "\\n\\n".join(f"[{r.file_name}]\\n{r.content}" for r in results)

        2. Renderează prompt "rag_answer" cu:
           - query=state.query
           - context=context

        3. Apelează LLM:
           answer = self.llm.generate_sync([{"role": "user", "content": prompt}])

        4. Determină status:
           - "success" dacă feedback.can_answer == True
           - "partial" dacă am răspuns dar fără can_answer
           - "failed" dacă nu avem rezultate

        5. Return {"answer": answer, "status": status}
        """
        logger.info("[ANSWER]")

        results = state.rag_result.results if state.rag_result else []

        # Nu avem pe ce să bazăm răspunsul → eșec onest, nu inventăm.
        if not results:
            return {
                "answer": "Nu am găsit informații relevante pentru a răspunde la întrebare.",
                "status": "failed",
            }

        # Generăm răspunsul final din context (text liber, NU JSON de data asta).
        context = _build_context(results)
        prompt = self.prompts.render("rag_answer", query=state.query, context=context)
        answer = self.llm.generate_sync([{"role": "user", "content": prompt}])

        # Status:
        #  - "success" dacă orchestratorul a confirmat can_answer la evaluare
        #  - "partial" dacă răspundem oricum (ex: am atins max_iterations fără confirmare)
        if state.feedback and state.feedback.can_answer:
            status = "success"
        else:
            status = "partial"

        return {"answer": answer, "status": status}

    # === ROUTING ===

    def _should_continue(self, state: OrchestratorState) -> Literal["call_rag", "answer"]:
        """Decide dacă continuăm căutarea sau răspundem."""
        if state.feedback and state.feedback.can_answer:
            return "answer"
        if state.iteration >= self.config.max_iterations:
            logger.info(f"[ROUTING] Max iterations ({self.config.max_iterations}) reached")
            return "answer"
        return "call_rag"

    # === GRAPH ===

    def build_graph(self):
        """Construiește graful Orchestrator."""
        graph = StateGraph(OrchestratorState)

        graph.add_node("call_rag", self.node_call_rag)
        graph.add_node("evaluate", self.node_evaluate)
        graph.add_node("answer", self.node_answer)

        graph.add_edge(START, "call_rag")
        graph.add_edge("call_rag", "evaluate")
        graph.add_conditional_edges(
            "evaluate",
            self._should_continue,
            {"call_rag": "call_rag", "answer": "answer"}
        )
        graph.add_edge("answer", END)

        return graph.compile()
