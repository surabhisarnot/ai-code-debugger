# AI Code Debugger (Phase 2: tools + agent loop)

Paste Python code, get a structured review: summary, architecture notes,
bugs with line numbers and evidence, and suggested fixes.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and click "Load sample", then "Analyze code".

Run the tests (no API key needed, they use a scripted fake model):

```bash
python -m pytest -q
```

## Layout

- `app/schema.py`  data shapes (request, finding, report)
- `app/tools.py`   real tools: parse_ast, run_linter (ruff), run_security_scan (bandit), get_lines
- `app/agent.py`   the agent loop: model picks tool -> we run it -> result goes back -> repeat
- `app/guards.py`  line numbering, evidence check, size limit
- `app/main.py`    FastAPI routes
- `static/index.html` the UI
- `tests/`         tool tests and agent-loop tests
