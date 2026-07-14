"""Lucky Cat receipt for the private signal topology compiler."""

import pytest


@pytest.mark.issue(683)
def test_lucky_cat_signal_graph_receipt(example_app) -> None:
    example_app.freeze()
    graph = example_app._runtime_state._signal_graph
    assert graph is not None

    assert len(graph.producers) == 10
    assert sum(edge.kind == "depends_on" for edge in graph.edges) == 5
    assert graph.producer("lobby_snapshot") is not None
    assert graph.producer("lobby_snapshot").source_kind == "lazy"
    assert graph.producer("notifications").audience == "session"

    market_sinks = graph.sink_ids_for("lobby_snapshot")
    bound_names = {binding.signal_name for binding in graph.bindings if binding.id in market_sinks}
    assert bound_names == {"featured", "market_stats", "movers"}
    assert all(binding.ownership == "resolved" for binding in graph.bindings)
