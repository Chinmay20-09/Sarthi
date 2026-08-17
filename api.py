"""
Sarthi API — FastAPI server.

ARCHITECTURE:
    Uses the three-layer architecture:
    - Skills (speech, scanner, launcher, browser)
    - Knowledge Layer (entity resolution, routing, caching)
    - Database Layer (SQLite persistence)

    Brain orchestrates everything. EventBus enables decoupled communication.
"""

import os
import sys

# Under pythonw (start.bat's windowless background mode) there is no
# console: sys.stdout/sys.stderr are None, which would crash uvicorn's
# logging setup and every print() in the request handlers. Route them to
# devnull so the API runs fine without a terminal window.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from brain.engine import BrainEngine
from brain.intent import Intent
from brain.modes import CONVERSATION_MODE, detect_mode_command, get_mode, set_mode
from events import get_bus
from hermes.routes import router as hermes_router
from knowledge.manager import get_manager
from skills.browser.routes import router as browser_router
from skills.registry import get_registry
from utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

app = FastAPI(title="Sarthi API")

# CORS — restrict cross-origin access to the local UI origins only.
# Sarthi runs on 127.0.0.1 and holds personal data (memories, chat
# transcripts, settings). A wildcard allowlist would let ANY website the
# user visits read GET /memory, /chat, /settings and even POST /command
# (open apps, remember facts, ...). Only the local UI may call the API
# cross-origin: the UI served by this API itself on :8000 (same origin,
# unaffected by CORS) and the static UI server on :5500 (dev + background).
LOCAL_UI_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_UI_ORIGINS,
    # No cookie/session auth exists, so cross-origin credentials are never
    # needed; keeping this False is the tightest valid configuration.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include router for browser skill
app.include_router(browser_router)

# Include router for Hermes local AI
app.include_router(hermes_router)

# Serve Frontend
app.mount("/ui", StaticFiles(directory="UI"), name="ui")

# Core
engine = BrainEngine()
knowledge = get_manager()
bus = get_bus()
skill_registry = get_registry()


class CommandRequest(BaseModel):
    text: str
    # Optional conversation session id (used by conversation mode so Hermes
    # remembers earlier turns of the same chat).
    session_id: str | None = None


class ModeRequest(BaseModel):
    mode: str


class CategorizeRequest(BaseModel):
    name: str
    status: str


class RunRequest(BaseModel):
    name: str


class SettingRequest(BaseModel):
    key: str
    value: str


class ChatMessageRequest(BaseModel):
    session_id: str
    role: str
    content: dict


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


def _mode_command_response(text: str, mode: str) -> dict:
    """Reply for a mode-switch command (e.g. "conversation mode", "/exit")."""
    if mode == CONVERSATION_MODE:
        message = (
            "Switched to conversation mode \u2014 I'll chat with you now and won't "
            "execute any tasks. Type /exit to go back to normal mode."
        )
    else:
        message = "Back to default mode \u2014 I'll execute your commands again."
    return {
        "action": "mode",
        "target": mode,
        "status": "completed",
        "success": True,
        "text": message,
        "result": {"source": "nlp", "message": message, "mode": mode},
        "error": None,
        "source": "nlp",
        "mode": mode,
    }


def _conversation_response(text: str, session_id: str | None) -> dict:
    """Plain conversational reply for conversation mode — no task execution.

    Goes straight to hermes.service.chat (the orchestrator's plain chat path),
    which deliberately skips the tool planner, so not even registered tools
    can run while in conversation mode.
    """
    try:
        from hermes.service import chat as hermes_chat

        response = hermes_chat(text, session_id=session_id)
    except Exception:
        return {
            "action": "conversation",
            "target": None,
            "status": "error",
            "success": False,
            "text": "I couldn't reach my language model right now. Check that Ollama is running.",
            "result": None,
            "error": "conversation unavailable",
            "source": "nlp",
            "mode": CONVERSATION_MODE,
        }

    if response.success:
        return {
            "action": "conversation",
            "target": None,
            "status": "completed",
            "success": True,
            "text": response.text,
            "result": {
                "source": "nlp",
                "message": response.text,
                "provider": response.provider,
                "model": response.model,
            },
            "error": None,
            "source": "nlp",
            "provider": response.provider,
            "model": response.model,
            "mode": CONVERSATION_MODE,
        }
    return {
        "action": "conversation",
        "target": None,
        "status": "error",
        "success": False,
        "text": response.error or "I couldn't think of an answer right now.",
        "result": None,
        "error": response.error,
        "source": "nlp",
        "mode": CONVERSATION_MODE,
    }


@app.post("/command")
def command(request: CommandRequest):
    """Process a text command through the brain pipeline."""
    bus.publish("intent_received", {"text": request.text}, source="api")

    # Mode commands ("conversation mode", "/exit", ...) work in every mode.
    mode_cmd = detect_mode_command(request.text)
    if mode_cmd is not None:
        result = _mode_command_response(request.text, set_mode(mode_cmd))
        result["input"] = request.text
        bus.publish("command_completed", result, source="api")
        return result

    # Conversation mode: pure chat — the brain pipeline is never invoked, so
    # no skill or task can execute.
    if get_mode() == CONVERSATION_MODE:
        result = _conversation_response(request.text, request.session_id)
        result["input"] = request.text
        bus.publish("command_completed", result, source="api")
        return result

    response = engine.process(request.text)
    result = response.to_api_dict()
    result["input"] = request.text
    result["mode"] = get_mode()
    bus.publish("command_completed", result, source="api")
    return result


@app.get("/mode")
def get_chat_mode():
    """Return the current chat mode (default | conversation)."""
    return {"success": True, "mode": get_mode()}


@app.post("/mode")
def set_chat_mode(request: ModeRequest):
    """Set the chat mode (conversation | default)."""
    return {"success": True, "mode": set_mode(request.mode)}


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

    # Modes apply to voice too: switching works by voice, and conversation
    # mode never runs the brain pipeline.
    mode_cmd = detect_mode_command(text)
    if mode_cmd is not None:
        result = _mode_command_response(text, set_mode(mode_cmd))
        result["input"] = text
        bus.publish("command_completed", result, source="api")
        return result

    if get_mode() == CONVERSATION_MODE:
        result = _conversation_response(text, session_id=None)
        result["input"] = text
        bus.publish("command_completed", result, source="api")
        return result

    response = engine.process(text)
    api_result = response.to_api_dict()
    api_result["input"] = text
    api_result["mode"] = get_mode()

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
        "last_scan": knowledge.last_scan,
    }


@app.get("/applications")
def list_applications():
    """List all discovered applications (with their user category)."""
    apps = knowledge.load_applications()
    return [
        {
            "name": app.get("name", ""),
            "category": app.get("category", "application"),
            "app_status": app.get("app_status", "unattended"),
        }
        for app in apps
    ]


@app.get("/applications/categories")
def application_categories():
    """Get applications grouped by user category (favourite / ignored / unattended)."""
    return {
        "favourite": knowledge.get_applications_by_status("favourite"),
        "ignored": knowledge.get_applications_by_status("ignored"),
        "unattended": knowledge.get_applications_by_status("unattended"),
    }


@app.get("/applications/favourites")
def list_favourites():
    """List the applications the user has marked as favourites."""
    return [
        {
            "name": app.get("name", ""),
            "category": app.get("category", "application"),
            "app_status": app.get("app_status", "favourite"),
        }
        for app in knowledge.get_applications_by_status("favourite")
    ]


@app.post("/applications/categorize")
def categorize_application(request: CategorizeRequest):
    """Move an application to a category (favourite / ignored / unattended)."""
    app = knowledge.categorize_application(request.name, request.status)
    if app is None:
        return {"success": False, "error": f"Application not found: {request.name}"}
    return {"success": True, "app": app}


@app.post("/applications/run")
def run_application(request: RunRequest):
    """Launch an application directly (Run Anyway — bypasses the favourites gate)."""
    from brain.intent import Intent
    from skills.app_launcher.main import AppLauncherSkill

    result = AppLauncherSkill().execute(Intent(action="run_anyway", target=request.name))
    return {
        "success": result.get("success", False),
        "status": result.get("status", "error"),
        "result": result.get("result"),
        "error": result.get("error"),
    }


@app.post("/settings")
def save_setting(request: SettingRequest):
    """Persist a user setting (e.g. github_username) so it survives restarts."""
    from database.manager import get_database
    from database.models import CREATE_SETTINGS

    db = get_database()
    db.create_table(CREATE_SETTINGS)
    db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (request.key, request.value),
    )
    logger.info(f"Saved setting: {request.key}")
    return {"success": True, "key": request.key, "value": request.value}


@app.get("/settings/{key}")
def get_setting(key: str):
    """Read a previously saved user setting by key."""
    from database.manager import get_database
    from database.models import CREATE_SETTINGS

    db = get_database()
    db.create_table(CREATE_SETTINGS)
    row = db.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
    return {"key": key, "value": row["value"] if row else None}


@app.get("/memory")
def list_memories():
    """List the facts the user saved with /remember (for the sidebar badge)."""
    from knowledge.memory import get_memory

    memories = get_memory().list_memories()
    return {
        "success": True,
        "count": len(memories),
        "memories": [{"key": m.get("key", ""), "value": m.get("value", "")} for m in memories],
    }


@app.get("/chat")
def get_chat(session_id: str):
    """Return the persisted transcript of one chat session (as rendered by the UI)."""
    import json

    from database.manager import get_database
    from database.models import CREATE_CHAT_MESSAGES

    db = get_database()
    db.create_table(CREATE_CHAT_MESSAGES)
    rows = db.fetch_all(
        "SELECT id, role, content FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    )
    for row in rows:
        try:
            row["content"] = json.loads(row["content"])
        except (TypeError, ValueError):
            row["content"] = {}
    return {"success": True, "count": len(rows), "messages": rows}


@app.post("/chat")
def add_chat_message(request: ChatMessageRequest):
    """Append one rendered message (user or assistant) to a chat session."""
    import json

    from database.manager import get_database
    from database.models import CREATE_CHAT_MESSAGES

    db = get_database()
    db.create_table(CREATE_CHAT_MESSAGES)
    db.execute(
        "INSERT INTO chat_messages (session_id, role, content, created_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (request.session_id, request.role, json.dumps(request.content, default=str)),
    )
    return {"success": True}


@app.delete("/chat")
def reset_chat(session_id: str):
    """Clear one chat session — the transcript AND Hermes' session context.

    Long-term /remember facts live in knowledge_memory and are deliberately
    left untouched, so resetting the chat never forgets what the user asked
    to remember.
    """
    from database.manager import get_database
    from database.models import CREATE_CHAT_MESSAGES, CREATE_CONVERSATION_MESSAGES
    from knowledge.memory import get_memory

    db = get_database()
    db.create_table(CREATE_CHAT_MESSAGES)
    db.create_table(CREATE_CONVERSATION_MESSAGES)
    db.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM conversation_messages WHERE session_id = ?", (session_id,))
    remembered = len(get_memory().list_memories())
    return {"success": True, "cleared": session_id, "remembered_facts": remembered}


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
