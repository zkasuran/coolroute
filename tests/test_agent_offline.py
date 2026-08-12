"""Proves the agent's tool-calling loop end to end with NO network: a scripted
fake reasoning model drives real tool execution against the mock backend.
"""
import json
from types import SimpleNamespace

from coolroute.agent import CoolRouteAgent
from coolroute.fortyguard import MockFortyGuardClient
from coolroute.tools import ToolRegistry


def _tool_call(call_id, name, args):
    return SimpleNamespace(id=call_id, type="function",
                           function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def _resp(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeLLM:
    """Returns scripted completions in order and records what it was sent."""

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._scripted.pop(0)


def _agent(scripted):
    llm = FakeLLM(scripted)
    return CoolRouteAgent(llm, "fake-model", ToolRegistry(MockFortyGuardClient()), max_steps=4), llm


def test_agent_runs_tool_then_answers():
    scripted = [
        _resp(tool_calls=[_tool_call("c1", "find_coolest_hour", {
            "latitude": 28.61, "longitude": 77.21, "date": "2024-07-15",
            "candidate_hours": [6, 12, 18], "duration_hours": 1})]),
        _resp(content="Start at 06:00, it is the coolest window."),
    ]
    agent, llm = _agent(scripted)
    result = agent.run("When is the coolest hour to work in Delhi?")

    assert "06:00" in result.final_text
    assert [s["tool"] for s in result.steps] == ["find_coolest_hour"]
    # the tool result really flowed back into the conversation
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert tool_msgs and "start_hour" in tool_msgs[0]["content"]
    # the model was offered the tool schemas
    assert llm.calls[0]["tools"], "tools were not passed to the model"


def test_agent_answers_without_tools():
    agent, _ = _agent([_resp(content="Stay indoors, it is 48C out.")])
    result = agent.run("Is it hot?")
    assert result.final_text.startswith("Stay indoors")
    assert result.steps == []


def test_agent_surfaces_tool_error_and_recovers():
    scripted = [
        _resp(tool_calls=[_tool_call("c1", "find_coolest_hour", {
            "latitude": 28.61, "longitude": 77.21, "date": "2099-01-01",
            "candidate_hours": [12]})]),  # beyond the 12h forecast cap -> tool error
        _resp(content="That date is outside the forecast window."),
    ]
    agent, _ = _agent(scripted)
    result = agent.run("Coolest hour on new year 2099?")
    assert result.steps[0]["result"]["error"] is True
    assert "forecast" in result.final_text.lower()
