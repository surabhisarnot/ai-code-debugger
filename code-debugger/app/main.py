from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent import run_agent
from app.schema import AnalyzeRequest

app = FastAPI(title="AI Code Debugger")
STATIC = Path(__file__).parent.parent / "static"


@app.post("/analyze")
def analyze_code(req: AnalyzeRequest):
    try:
        return run_agent(req.code, req.language)
    except ValueError as e:  # e.g. code too long
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {e}")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
