"""
Test izolat pentru node_evaluate + node_answer — FĂRĂ DB, FĂRĂ cheie API.
Rulează din src/:  python test_orchestrator_local.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skillab-py" / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import Orchestrator
from state import OrchestratorState, RAGSearchResult, SearchResultItem, OrchestratorFeedback


class FakeLLM:
    model = "fake"
    def __init__(self, response): self._r = response
    def generate_sync(self, messages): return self._r


def _state_cu_rezultate():
    return OrchestratorState(
        query="Care e totalul facturilor TechSoft?",
        rag_result=RAGSearchResult(
            query_used="facturi TechSoft",
            results=[SearchResultItem(
                content="Factura 0004 TechSoft, total 12.000 RON",
                summary="factură", file_name="factura_0004_techsoft.docx", score=0.6,
            )],
            max_score=0.6, avg_score=0.6,
        ),
    )


def test_evaluate_poate_raspunde():
    orch = Orchestrator(llm=FakeLLM('```json\n{"can_answer": true}\n```'))
    out = orch.node_evaluate(_state_cu_rezultate())
    assert out["feedback"].can_answer is True
    print("✓ evaluate: parsează can_answer=true")


def test_evaluate_fara_rezultate():
    orch = Orchestrator(llm=FakeLLM("nu ar trebui apelat"))
    out = orch.node_evaluate(OrchestratorState(query="ceva"))
    assert out["feedback"].can_answer is False
    print("✓ evaluate: fără chunks → can_answer=false, fără LLM")


def test_answer_success():
    orch = Orchestrator(llm=FakeLLM("Totalul facturilor TechSoft este 12.000 RON."))
    st = _state_cu_rezultate()
    st.feedback = OrchestratorFeedback(can_answer=True)
    out = orch.node_answer(st)
    assert out["status"] == "success"
    assert "12.000" in out["answer"]
    print("✓ answer: can_answer=true → status success")


def test_answer_partial():
    orch = Orchestrator(llm=FakeLLM("Răspuns parțial din ce am găsit."))
    out = orch.node_answer(_state_cu_rezultate())  # fără feedback confirmat
    assert out["status"] == "partial"
    print("✓ answer: fără can_answer → status partial")


def test_answer_failed():
    orch = Orchestrator(llm=FakeLLM("nu ar trebui apelat"))
    out = orch.node_answer(OrchestratorState(query="ceva"))
    assert out["status"] == "failed"
    print("✓ answer: fără chunks → status failed")


if __name__ == "__main__":
    test_evaluate_poate_raspunde()
    test_evaluate_fara_rezultate()
    test_answer_success()
    test_answer_partial()
    test_answer_failed()
    print("\nToate testele au trecut ✓")