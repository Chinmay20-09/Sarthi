"""
Sarthi API — FastAPI server.

ARCHITECTURE:
    Uses the three-layer architecture:
    - Skills (speech, scanner, launcher, browser)
    - Knowledge Layer (entity resolution, routing, caching)
    - Database Layer (SQLite persistence)

    Brain orchestrates everything. EventBus enables decoupled communication.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from brain.engine import BrainEngine
from brain.intent import Intent
from events import get_bus
from knowledge.manager import get_manager
from skills.registry import get_registry
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

# Serve Frontend
app.mount("/ui", StaticFiles(directory="UI"), name="ui")

# Core
engine = BrainEngine()
knowledge = get_manager()
bus = get_bus()
skill_registry = get_registry()


class CommandRequest(BaseModel):
    text: str


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/dashboard.html")


@app.get("/health")
def health():
    return {
        "assistant": "Sarthi",
        "status": "Running",
        "architecture": "three_layer",
    }


@app.post("/command")
def command(request: CommandRequest):
    """Process a text command through the brain pipeline."""
    bus.publish("intent_received", {"text": request.text}, source="api")
    response = engine.process(request.text)
    result = response.to_api_dict()
    result["text"] = request.text
    bus.publish("command_completed", result, source="api")
    return result


@app.post("/listen")
def listen_command():
    """Process a voice command using SpeechSkill (lazy-loaded)."""
    bus.publish("voice_command_received", {}, source="api")

    # Lazy-load speech skill to avoid startup crash if Whisper unavailable
    try:
        speech_skill = skill_registry.get_skill("speech")
        if speech_skill is None:
            logger.error("Speech skill not available")
            return {"success": False, "status": "error", "error": "Speech not available"}
        result = speech_skill.execute(Intent(action="listen"))
        text = result.get("result", {}).get("text", "")
    except Exception as e:
        logger.error(f"Speech recognition failed: {e}")
        return {"success": False, "status": "error", "error": str(e)}

    if not text:
        return {"success": False, "status": "error", "error": "No speech recognized"}

    logger.info(f"Speech: {text}")
    bus.publish("speech_recognized", {"text": text}, source="api")

    response = engine.process(text)
    api_result = response.to_api_dict()
    api_result["text"] = text

    bus.publish("command_completed", api_result, source="api")
    return api_result


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
def list_applications():
    """List all discovered applications."""
    apps = knowledge.load_applications()
    return [{"name": app["name"], "category": app["category"]} for app in apps]


@app.get("/skills")
def list_skills():
    """List all installed skills via the SkillRegistry."""
    return skill_registry.list_skills()


@app.get("/skills/{skill_id}")
def get_skill(skill_id: str):
    """Get metadata for a specific skill."""
    metadata = skill_registry.get_metadata(skill_id)
    if metadata is None:
        return {"error": f"Skill not found: {skill_id}"}
    return metadata.to_dict()


@app.post("/skills/{skill_id}/enable")
def enable_skill(skill_id: str):
    """Enable a skill."""
    success = skill_registry.enable(skill_id)
    return {"success": success, "skill_id": skill_id}


@app.post("/skills/{skill_id}/disable")
def disable_skill(skill_id: str):
    """Disable a skill."""
    success = skill_registry.disable(skill_id)
    return {"success": success, "skill_id": skill_id}


@app.get("/events/history")
def event_history():
    """Get recent event history (for debugging)."""
    return [
        {
            "name": e.name,
            "data": e.data,
            "source": e.source,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in bus.history[-20:]
    ]


if __name__ == "__main__":
    import uvicorn

    bus.publish("system_startup", {}, source="api")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
from skills.browser.routes import router as browser_router

app.include_router(browser_router)
