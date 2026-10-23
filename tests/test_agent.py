"""Automated checks used by CI. They never call the real web or Gemini API."""
import pytest

import agent


def test_extract_bullets_handles_different_markers():
    text = "Intro line\n- first\n* second\n3. third\n- fourth"
    assert agent.extract_bullets(text) == ["first", "second", "third", "fourth"]


def test_extract_bullets_joins_wrapped_lines():
    assert agent.extract_bullets("- first part\n  continues here\n- second") == [
        "first part continues here", "second"]


def test_format_results_contains_title_and_source():
    out = agent.format_results([{"title": "T", "body": "B", "href": "http://x"}])
    assert "T" in out and "B" in out and "http://x" in out


def test_workflow_chains_search_then_summary(monkeypatch):
    order = []
    monkeypatch.setattr(agent, "search_web", lambda t: order.append("search") or "RESULTS")
    monkeypatch.setattr(agent, "summarize", lambda t, r, temp: order.append("summarize") or "- a\n- b\n- c")
    assert agent.run_workflow("topic", progress=lambda m: None) == "- a\n- b\n- c"
    assert order == ["search", "summarize"]


def test_empty_topic_rejected():
    with pytest.raises(ValueError):
        agent.run_workflow("   ", progress=lambda m: None)


def test_summarize_returns_exactly_three_bullets(monkeypatch):
    monkeypatch.setattr(agent, "_call_gemini", lambda t, r, temp: "- 1\n- 2\n- 3\n- 4")
    assert agent.summarize("t", "r").count("- ") == 3
