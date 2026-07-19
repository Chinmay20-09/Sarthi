"""
Sarthi API — FastAPI server.

Endpoints:
    GET  /             — Health check
    POST /command      — Process a text command
    POST /listen       — Process a voice command
    GET  /knowledge    — Knowledge base statistics
    GET  /applications — List all applications
    GET  /skills       — List all installed skills
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from brain.engine import BrainEngine
from knowledge.manager import get_manager
from skills.manager import load_skills
from skills.speech_recognition.listener import listen
from utils.logger import get_logger, setup_logging

setup_logging()

logger = get_logger(__name__)

app = FastAPI(title="Sarthi API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = BrainEngine()
knowledge = get_manager()


class CommandRequest(BaseModel):
    """Request model for POST /command."""

    text: str


@app.get("/")
def home():
    """Health check endpoint."""
    return {"assistant": "Sarthi", "status": "Running"}


@app.post("/command")
def command(request: CommandRequest):
    """Process a text command through the brain pipeline."""
    response = engine.process(request.text)
    result = response.to_api_dict()
    result["text"] = request.text
    return result


@app.get("/knowledge")
def knowledge_stats():
    """Get knowledge base statistics."""
    applications = knowledge.load_applications()

    games = [app for app in applications if app.get("category") == "game"]
    apps = [app for app in applications if app.get("category") != "game"]

    return {
        "total": len(applications),
        "applications": len(apps),
        "games": len(games),
        "last_scan": None,
    }


@app.get("/applications")
def applications():
    apps = knowledge.load_applications()

    return [{"name": app["name"], "category": app["category"]} for app in apps]


@app.get("/skills")
def get_skills():
    """List all installed skills."""
    return load_skills()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)


@app.post("/listen")
def listen_command():
    """Record audio, transcribe, and process through the brain pipeline."""
    text = listen()
    logger.info(f"🎤 Whisper : {text}")

    response = engine.process(text)

    result = response.to_api_dict()
    result["text"] = text
    return result
