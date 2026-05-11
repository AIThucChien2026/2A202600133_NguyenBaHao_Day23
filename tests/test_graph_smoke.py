import importlib.util
from unittest.mock import Mock, patch

import pytest

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Route, Scenario, initial_state

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="langgraph not installed in local environment",
)


def make_mock_llm(route: str = "simple", risk_level: str = "low") -> Mock:
    """Tạo mock LLM trả về kết quả cố định."""
    mock_result = Mock()
    mock_result.route = route
    mock_result.risk_level = risk_level
    mock_result.evaluation_result = "success"
    mock_result.content = "Mock response for testing."

    mock_llm = Mock()
    mock_llm.invoke.return_value = mock_result
    mock_llm.with_structured_output.return_value = mock_llm
    return mock_llm


@pytest.mark.parametrize(
    ("query", "expected_route"),
    [
        ("How do I reset my password?", Route.SIMPLE.value),
        ("Please lookup order status for order 123", Route.TOOL.value),
        ("Refund this customer", Route.RISKY.value),
    ],
)
def test_graph_runs_basic_routes(query: str, expected_route: str) -> None:
    with patch(
        "langgraph_agent_lab.nodes.get_llm",
        return_value=make_mock_llm(route=expected_route),
    ):
        graph = build_graph(checkpointer=build_checkpointer("memory"))
        scenario = Scenario(
            id="smoke", query=query, expected_route=Route(expected_route)
        )
        state = initial_state(scenario)
        result = graph.invoke(
            state, config={"configurable": {"thread_id": state["thread_id"]}}
        )
        assert result["route"] == expected_route
        assert result.get("final_answer") or result.get("pending_question")
