"""Tests for the tools and for the agent loop (using a scripted fake model,
so they cost nothing and need no API key)."""
from types import SimpleNamespace as NS

import pytest

from app import agent, tools

SAMPLE = '''def average(nums):
    total = 0
    for i in range(1, len(nums)):
        total += nums[i]
    return total / len(nums)

def find_user(db, name):
    query = "SELECT * FROM users WHERE name = '" + name + "'"
    return db.execute(query)
'''

GOOD_REPORT = {
    "summary": "s", "walkthrough": "w", "architecture_notes": "a",
    "findings": [{
        "title": "Off by one", "severity": "high", "category": "bug",
        "line_start": 3, "line_end": 3, "evidence": "range(1, len(nums))",
        "explanation": "skips first item", "suggested_fix": "range(len(nums))",
        "confirmed_by": None,
    }],
    "improvements": ["add tests"],
}


# ---- fake model helpers
def tool_use(name, args, id):
    return NS(type="tool_use", name=name, input=args, id=id)


def reply(*blocks):
    return NS(content=list(blocks), usage=NS(input_tokens=10, output_tokens=5))


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


# ---- tool tests
def test_parse_ast_finds_functions():
    result = tools.parse_ast(SAMPLE)
    assert [f["name"] for f in result["functions"]] == ["average", "find_user"]


def test_parse_ast_reports_syntax_error():
    assert "syntax_error" in tools.parse_ast("def broken(:\n    pass")


def test_linter_and_scanner_run():
    assert "issue_count" in tools.run_linter(SAMPLE)
    scan = tools.run_security_scan(SAMPLE)
    assert any(i["rule"] == "B608" for i in scan["issues"])  # SQL injection


def test_get_lines_and_unknown_tool():
    assert tools.get_lines(SAMPLE, 1, 2).startswith("1 | def average")
    text, is_error = tools.run_tool("nope", {}, SAMPLE)
    assert is_error


# ---- agent loop tests
def test_full_loop_runs_tools_then_submits(monkeypatch):
    bad = dict(GOOD_REPORT, findings=GOOD_REPORT["findings"] + [
        dict(GOOD_REPORT["findings"][0], evidence="code that is not there")])
    fake = FakeClient([
        reply(tool_use("parse_ast", {}, "t1")),
        reply(tool_use("run_security_scan", {}, "t2")),
        reply(tool_use("submit_report", bad, "t3")),
    ])
    monkeypatch.setattr(agent, "client", fake)
    out = agent.run_agent(SAMPLE)
    assert [t["tool"] for t in out["trace"]] == ["parse_ast", "run_security_scan"]
    assert len(out["report"].findings) == 1      # invented one was dropped
    assert out["dropped_findings"] == 1
    assert out["usage"]["input_tokens"] == 30


def test_bad_schema_is_sent_back_and_retried(monkeypatch):
    broken = dict(GOOD_REPORT, findings="not a list")
    fake = FakeClient([
        reply(tool_use("submit_report", broken, "t1")),
        reply(tool_use("submit_report", GOOD_REPORT, "t2")),
    ])
    monkeypatch.setattr(agent, "client", fake)
    out = agent.run_agent(SAMPLE)
    assert len(out["report"].findings) == 1
    result_msgs = [m for m in fake.calls[1]["messages"]
                   if m["role"] == "user" and isinstance(m["content"], list)]
    assert result_msgs[0]["content"][0]["type"] == "tool_result"
    assert result_msgs[0]["content"][0]["is_error"]


def test_step_limit_stops_runaway_agent(monkeypatch):
    fake = FakeClient([reply(tool_use("parse_ast", {}, f"t{i}"))
                       for i in range(agent.MAX_STEPS)])
    monkeypatch.setattr(agent, "client", fake)
    with pytest.raises(RuntimeError):
        agent.run_agent(SAMPLE)
    last_tools = fake.calls[-1]["tools"]
    assert [t["name"] for t in last_tools] == ["submit_report"]  # forced finish
