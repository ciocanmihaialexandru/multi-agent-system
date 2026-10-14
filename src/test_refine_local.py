"""
Test izolat pentru node_refine — FĂRĂ DB și FĂRĂ cheie API.

Rulează din folderul src/:
    python test_refine_local.py

Ideea: înlocuim LLM-ul real cu un "FakeLLM" care întoarce un JSON prefabricat,
ca să testăm doar LOGICA noastră din node_refine (cele două ramuri + parsarea),
nu și apelul real către model.
"""
import sys
from pathlib import Path

# Aceleași căi ca în main.py, ca importurile skillab + state să meargă.
sys.path.insert(0, str(Path(__file__).parent.parent / "skillab-py" / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from rag_agent import RAGAgent, RAGAgentConfig
from state import RAGAgentState, RAGSearchResult, SearchResultItem, OrchestratorFeedback


class FakeLLM:
    """LLM fals: nu apelează niciun API, doar întoarce un răspuns fix."""
    model = "fake"

    def __init__(self, canned_response: str):
        self._response = canned_response

    def generate_sync(self, messages):
        # Afișăm promptul primit, ca să vezi că render-ul a mers.
        print("\n--- PROMPT trimis către LLM ---")
        print(messages[0]["content"][:400], "...\n")
        return self._response


def test_fara_feedback():
    """Prima iterație: fără feedback → trebuie să întoarcă query-ul original."""
    agent = RAGAgent(llm=FakeLLM("nu ar trebui apelat"), config=RAGAgentConfig())
    state = RAGAgentState(query="Care e totalul facturilor TechSoft?")

    out = agent.node_refine(state)

    assert out["refined"].query == "Care e totalul facturilor TechSoft?"
    assert out["refined"].threshold is None
    print("✓ test_fara_feedback: query păstrat, fără apel LLM")


def test_cu_feedback():
    """Cu feedback → trebuie să cheme LLM-ul și să parseze RefinedQuery."""
    fake_json = '```json\n{"query": "total facturi TechSoft SRL 2024", "threshold": 0.3}\n```'
    agent = RAGAgent(llm=FakeLLM(fake_json), config=RAGAgentConfig())

    state = RAGAgentState(
        query="Care e totalul facturilor TechSoft?",
        feedback=OrchestratorFeedback(
            can_answer=False,
            missing_info="suma exactă nu apare",
            suggestion="caută după numele complet al firmei",
        ),
        result=RAGSearchResult(
            query_used="facturi TechSoft",
            results=[SearchResultItem(
                content="Factura 0004 TechSoft...", summary="factură TechSoft",
                file_name="factura_0004_techsoft_202406.docx", score=0.21,
            )],
            max_score=0.21, avg_score=0.21,
        ),
    )

    out = agent.node_refine(state)

    assert out["refined"].query == "total facturi TechSoft SRL 2024"
    assert out["refined"].threshold == 0.3
    print("✓ test_cu_feedback: query rafinat + threshold ajustat")


if __name__ == "__main__":
    test_fara_feedback()
    test_cu_feedback()
    print("\nToate testele au trecut ✓")
