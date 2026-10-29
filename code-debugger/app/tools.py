"""Real tools the agent can call.

These only ANALYZE the code. None of them executes it.
(Running code safely is Phase 3, in a sandbox.)

Each tool is a normal Python function. TOOL_DEFINITIONS is the menu we show
the model, and run_tool() is how we run whichever one it picks.
"""
import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_OUTPUT_CHARS = 6000  # keep tool results small so they do not flood the context
MAX_ITEMS = 30
TOOL_TIMEOUT = 20  # seconds


# ---------------------------------------------------------------- parse_ast
def _complexity(node: ast.AST) -> int:
    """Rough cyclomatic complexity: 1 + number of branches."""
    score = 1
    for n in ast.walk(node):
        if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While,
                          ast.ExceptHandler, ast.IfExp, ast.comprehension)):
            score += 1
        elif isinstance(n, ast.BoolOp):
            score += len(n.values) - 1
    return score


def _called_names(node: ast.AST) -> list[str]:
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return sorted(names)[:15]


def _describe_function(fn, owner: str | None = None) -> dict:
    return {
        "name": f"{owner}.{fn.name}" if owner else fn.name,
        "line_start": fn.lineno,
        "line_end": fn.end_lineno,
        "args": [a.arg for a in fn.args.args],
        "complexity": _complexity(fn),
        "calls": _called_names(fn),
    }


def parse_ast(code: str) -> dict:
    """Structure of the code: imports, functions, classes, call names, complexity."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"syntax_error": {"line": e.lineno, "message": e.msg}}

    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    imports, functions, classes = [], [], []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "(relative)")
        elif isinstance(node, func_types):
            functions.append(_describe_function(node))
        elif isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "line_start": node.lineno,
                "line_end": node.end_lineno,
                "methods": [_describe_function(m, node.name)
                            for m in node.body if isinstance(m, func_types)],
            })
    has_main_guard = any(
        isinstance(n, ast.If) and "__name__" in ast.dump(n.test) for n in tree.body
    )
    return {
        "total_lines": len(code.splitlines()),
        "imports": imports,
        "functions": functions,
        "classes": classes,
        "has_main_guard": has_main_guard,
    }


# ------------------------------------------------------ linter and scanner
def _run_on_temp_file(code: str, build_cmd) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "code.py"
        path.write_text(code)
        return subprocess.run(
            build_cmd(str(path)), capture_output=True, text=True,
            timeout=TOOL_TIMEOUT, cwd=d,
        )


def run_linter(code: str) -> dict:
    """ruff: unused variables, undefined names, likely bugs, simplifications."""
    proc = _run_on_temp_file(code, lambda f: [
        sys.executable, "-m", "ruff", "check", "--isolated", "--exit-zero",
        "--output-format", "json", "--select", "E,F,B,SIM", "--ignore", "E501", f,
    ])
    if not proc.stdout.strip():
        return {"error": proc.stderr.strip()[:500] or "ruff returned no output"}
    issues = json.loads(proc.stdout)
    return {
        "issue_count": len(issues),
        "issues": [
            {"rule": i.get("code"), "line": i["location"]["row"], "message": i["message"]}
            for i in issues[:MAX_ITEMS]
        ],
    }


def run_security_scan(code: str) -> dict:
    """bandit: common Python security problems (SQL injection, eval, weak crypto...)."""
    proc = _run_on_temp_file(code, lambda f: [
        sys.executable, "-m", "bandit", "-q", "--exit-zero", "-f", "json", f,
    ])
    if not proc.stdout.strip():
        return {"error": proc.stderr.strip()[:500] or "bandit returned no output"}
    data = json.loads(proc.stdout)
    results = data.get("results", [])
    return {
        "issue_count": len(results),
        "issues": [
            {
                "rule": r["test_id"],
                "line": r["line_number"],
                "severity": r["issue_severity"],
                "confidence": r["issue_confidence"],
                "message": r["issue_text"],
            }
            for r in results[:MAX_ITEMS]
        ],
    }


# ---------------------------------------------------------------- get_lines
def get_lines(code: str, start: int, end: int) -> str:
    lines = code.splitlines()
    start = max(1, int(start))
    end = min(int(end), len(lines), start + 79)  # at most 80 lines
    if start > end:
        return "No lines in that range."
    return "\n".join(f"{i} | {lines[i - 1]}" for i in range(start, end + 1))


# ------------------------------------------------- menu shown to the model
TOOL_DEFINITIONS = [
    {
        "name": "parse_ast",
        "description": "Parse the code and return its structure: imports, functions "
        "(with line ranges, arguments, complexity, and what they call), classes, "
        "and whether it has a __main__ guard. Also reports syntax errors. "
        "Call this first to understand the code.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_linter",
        "description": "Run the ruff linter. Returns rule codes, line numbers and "
        "messages for likely bugs and code-quality problems.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_security_scan",
        "description": "Run the bandit security scanner. Returns rule ids, line "
        "numbers and severities for security problems.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_lines",
        "description": "Return specific numbered lines of the code (max 80) so you "
        "can inspect a region closely.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "integer", "description": "First line, 1-indexed"},
                "end": {"type": "integer", "description": "Last line, inclusive"},
            },
            "required": ["start", "end"],
        },
    },
]


def run_tool(name: str, args: dict, code: str) -> tuple[str, bool]:
    """Run one tool. Returns (result_text, is_error)."""
    try:
        if name == "parse_ast":
            result = parse_ast(code)
        elif name == "run_linter":
            result = run_linter(code)
        elif name == "run_security_scan":
            result = run_security_scan(code)
        elif name == "get_lines":
            result = get_lines(code, args["start"], args["end"])
        else:
            return f"Unknown tool: {name}", True
    except subprocess.TimeoutExpired:
        return f"{name} timed out after {TOOL_TIMEOUT}s.", True
    except Exception as e:  # a broken tool should not crash the whole run
        return f"{name} failed: {e}", True

    text = result if isinstance(result, str) else json.dumps(result, indent=1)
    return text[:MAX_OUTPUT_CHARS], False
