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
from datetime import datetime

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
from brain.modes import (
    CONVERSATION_MODE,
    detect_mode_command,
    get_mode,
    get_test_mode,
    set_mode,
    set_test_mode,
)
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


@app.delete("/command-history/{cmd_id}")
def delete_command_history_entry(cmd_id: int):
    """Delete a single command history entry by id."""
    from database.manager import get_database
    from database.models import CREATE_COMMAND_HISTORY

    db = get_database()
    db.create_table(CREATE_COMMAND_HISTORY)
    db.execute("DELETE FROM command_history WHERE id = ?", (cmd_id,))
    return {"success": True, "deleted_id": cmd_id}


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


@app.delete("/memory/{key}")
def delete_memory(key: str):
    """Delete a single saved memory by key."""
    from knowledge.memory import get_memory

    success = get_memory().forget_long(key)
    if not success:
        return {"success": False, "error": f"Memory not found or failed to delete: {key}"}
    return {"success": True, "deleted": key}


@app.get("/command-history")
def command_history():
    """Recent command history for the Memory page."""
    from knowledge.memory import get_memory

    entries = get_memory().get_history(limit=30)
    return {
        "success": True,
        "count": len(entries),
        "history": [
            {
                "id": e.get("id"),
                "command": e.get("command", ""),
                "action": e.get("action", ""),
                "target": e.get("target", ""),
                "success": bool(e.get("success")),
                "timestamp": e.get("timestamp", ""),
            }
            for e in entries
        ],
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


@app.get("/system/metrics")
def system_metrics():
    """Return live CPU, RAM, SSD (disk), and GPU utilization."""
    from reading import get_system_metrics

    return get_system_metrics()


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


def _save_metrics_chart(metrics: list[dict], summary: dict, path: Path) -> None:
    """Render a simple metrics chart (Pillow) and save as PNG.

    Draws a dark-themed chart with:
      - Bar chart for passed / failed counts
      - Line overlays for temperature (°C) and GPU utilisation (%)
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return  # Pillow not installed — skip silently

    W, H = 900, 360
    PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 70, 70, 50, 50
    BG = (14, 14, 14)
    GRID = (40, 40, 40)
    TEXT = (187, 201, 206)
    CYAN = (0, 217, 255)
    RED = (255, 107, 107)
    ORANGE = (255, 183, 125)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("consola.ttf", 11)
        font_sm = ImageFont.truetype("consola.ttf", 9)
        font_lg = ImageFont.truetype("consola.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font
        font_lg = font

    plot_x = PAD_LEFT
    plot_y = PAD_TOP
    plot_w = W - PAD_LEFT - PAD_RIGHT
    plot_h = H - PAD_TOP - PAD_BOTTOM

    # Title
    draw.text((W // 2, 16), "SYSTEM METRICS DURING TEST", fill=CYAN, font=font_lg, anchor="mt")

    # Grid lines
    for i in range(5):
        y = plot_y + int(plot_h * i / 4)
        draw.line([(plot_x, y), (plot_x + plot_w, y)], fill=GRID, width=1)

    n = len(metrics)
    if n < 2:
        img.save(str(path))
        return

    x_step = plot_w / (n - 1)
    dense = n > 15  # adaptive layout for many data points
    dot_r = 2 if dense else 3

    # ── Bars: passed / failed (start + end only when dense) ──
    bar_w = max(3, int(min(x_step * 0.35, 12)))
    max_count = max(summary.get("total", 1), 1)
    bar_indices = [0, n - 1] if dense else range(n)
    for i in bar_indices:
        cx = plot_x + int(i * x_step)
        bar_h = int((summary.get("passed", 0) / max_count) * plot_h * 0.6)
        if bar_h > 0:
            draw.rectangle(
                [cx - bar_w, plot_y + plot_h - bar_h, cx, plot_y + plot_h],
                fill=(0, 217, 255, 60), outline=CYAN,
            )
        bar_h_f = int((summary.get("failed", 0) / max_count) * plot_h * 0.6)
        if bar_h_f > 0:
            draw.rectangle(
                [cx, plot_y + plot_h - bar_h_f, cx + bar_w, plot_y + plot_h],
                fill=(255, 107, 107, 60), outline=RED,
            )

    # ── Line: temperature ──
    temps = [m.get("temperature") for m in metrics]
    valid_temps = [t for t in temps if t is not None]
    if valid_temps:
        max_temp = max(valid_temps) * 1.15 or 100
        points = []
        for i, t in enumerate(temps):
            if t is None:
                continue
            x = plot_x + int(i * x_step)
            y = plot_y + plot_h - int((t / max_temp) * plot_h)
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=ORANGE, width=2)
        for x, y in points:
            draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r], fill=ORANGE)
        draw.text((W - PAD_RIGHT + 8, plot_y), f"{max_temp:.0f}°C", fill=ORANGE, font=font_sm)
        draw.text((W - PAD_RIGHT + 8, plot_y + plot_h - 10), "0°C", fill=ORANGE, font=font_sm)

    # ── Line: GPU % ──
    gpus = [m.get("gpu_percent", 0) for m in metrics]
    points_gpu = []
    for i, g in enumerate(gpus):
        x = plot_x + int(i * x_step)
        y = plot_y + plot_h - int((g / 100) * plot_h)
        points_gpu.append((x, y))
    if len(points_gpu) > 1:
        draw.line(points_gpu, fill=CYAN, width=2)
    for x, y in points_gpu:
        draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r], fill=CYAN)

    # ── Line: CPU % ──
    cpus = [m.get("cpu_percent", 0) for m in metrics]
    points_cpu = []
    for i, c in enumerate(cpus):
        x = plot_x + int(i * x_step)
        y = plot_y + plot_h - int((c / 100) * plot_h)
        points_cpu.append((x, y))
    if len(points_cpu) > 1:
        draw.line(points_cpu, fill=(174, 236, 255), width=1)
    for x, y in points_cpu:
        draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(174, 236, 255))

    # ── X-axis labels (skip when dense to avoid overlap) ──
    label_step = max(1, n // 10) if dense else 1
    for i, m in enumerate(metrics):
        is_endpoint = m["index"] == 0 or m["index"] == summary.get("total", 0)
        if not is_endpoint and (i % label_step != 0):
            continue
        x = plot_x + int(i * x_step)
        label = "Start" if m["index"] == 0 else (
            "End" if m["index"] == summary.get("total", 0) else f"#{m['index']}")
        draw.text((x, plot_y + plot_h + 8), label, fill=TEXT, font=font_sm, anchor="mt")

    # ── Left Y-axis labels ──
    for i in range(5):
        y = plot_y + plot_h - int(plot_h * i / 4)
        val = int(max_count * i / 4)
        draw.text((plot_x - 8, y), str(val), fill=TEXT, font=font_sm, anchor="rm")

    # ── Right Y-axis: GPU/CPU % ──
    for i in range(5):
        y = plot_y + plot_h - int(plot_h * i / 4)
        val = int(100 * i / 4)
        draw.text((plot_x + plot_w + 8, y), f"{val}%", fill=CYAN, font=font_sm, anchor="lm")

    # ── Legend ──
    legend_y = H - 14
    legend_items = [
        (CYAN, "■ PASSED"),
        (RED, "■ FAILED"),
        (ORANGE, "● TEMP"),
        (CYAN, "● GPU"),
        ((174, 236, 255), "● CPU"),
    ]
    lx = W // 2 - 160
    for color, label in legend_items:
        draw.text((lx, legend_y), label, fill=color, font=font_sm)
        lx += 80

    img.save(str(path))


def _csv(val) -> str:
    """Escape a value for inclusion in a CSV cell."""
    s = str(val if val is not None else "")
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


# Retention: delete run files older than this many days.  Set to 0 to keep forever.
RESULTS_RETENTION_DAYS = 30


def _cleanup_old_results(results_dir: Path) -> int:
    """Delete run_*.json and run_*.csv older than RESULTS_RETENTION_DAYS.

    Returns the number of files deleted.
    """
    if RESULTS_RETENTION_DAYS <= 0 or not results_dir.is_dir():
        return 0

    cutoff = datetime.now().timestamp() - (RESULTS_RETENTION_DAYS * 86400)
    deleted = 0
    for f in results_dir.iterdir():
        if f.suffix in (".json", ".csv") and f.stem.startswith("run_"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
    return deleted


@app.get("/test/prompts")
def get_test_prompts():
    """Load the list of test prompts from test_prompts.json."""
    import json
    from pathlib import Path

    path = Path(__file__).parent / "test_prompts.json"
    if not path.exists():
        return {"success": True, "prompts": []}
    try:
        prompts = json.loads(path.read_text(encoding="utf-8"))
        return {"success": True, "prompts": prompts}
    except (json.JSONDecodeError, OSError) as exc:
        return {"success": False, "error": str(exc), "prompts": []}


@app.post("/test/run")
def run_test_prompts():
    """Run every prompt in test_prompts.json through the brain engine.

    Returns the actual response text and whether the expected substring
    (if any) was found in the response.
    """
    import json
    import time
    from pathlib import Path

    path = Path(__file__).parent / "test_prompts.json"
    if not path.exists():
        return {"success": False, "error": "test_prompts.json not found"}

    try:
        prompts = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"success": False, "error": str(exc)}

    if not prompts:
        return {"success": True, "results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}

    def _sample_metrics() -> dict:
        """Snapshot of temperature, GPU utilisation, and CPU utilisation."""
        from reading import read_cpu, read_cpu_temperature, read_gpu

        cpu = read_cpu()
        temp = read_cpu_temperature()
        gpu = read_gpu()
        return {
            "cpu_percent": cpu.get("percent", 0),
            "temperature": temp.get("current") if temp else None,
            "gpu_percent": gpu.get("utilization_percent", 0) if gpu else 0,
        }

    # Capture baseline system metrics before the run
    metrics_timeline: list[dict] = []
    metrics_timeline.append({"index": 0, **_sample_metrics()})

    # Enable test mode so skills report what would happen without side-effects
    was_test = get_test_mode()
    set_test_mode(True)
    try:
        results = []
        for idx, entry in enumerate(prompts):
            prompt_text = entry.get("prompt", "")
            expected = entry.get("expected", "")
            start = time.time()
            try:
                response = engine.process(prompt_text)
                elapsed_ms = round((time.time() - start) * 1000)
                api = response.to_api_dict()
                actual = api.get("text", "") or ""
                if expected:
                    passed = expected.lower() in actual.lower()
                else:
                    passed = response.success
                results.append({
                    "prompt": prompt_text,
                    "expected": expected,
                    "actual": actual,
                    "success": response.success,
                    "passed": passed,
                    "action": api.get("action", ""),
                    "target": api.get("target", ""),
                    "elapsed_ms": elapsed_ms,
                })
            except Exception as exc:
                elapsed_ms = round((time.time() - start) * 1000)
                results.append({
                    "prompt": prompt_text,
                    "expected": expected,
                    "actual": str(exc),
                    "success": False,
                    "passed": False,
                    "action": "",
                    "target": "",
                    "elapsed_ms": elapsed_ms,
                })
            # Sample system metrics after every prompt for a smooth graph
            metrics_timeline.append({"index": idx + 1, **_sample_metrics()})
    finally:
        set_test_mode(was_test)

    # Final sample after test mode is restored
    metrics_timeline.append({"index": len(prompts), **_sample_metrics()})

    passed = sum(1 for r in results if r["passed"])
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
    }

    # Auto-save results to results/ directory (JSON + CSV)
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    _cleanup_old_results(results_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON
    json_path = results_dir / f"run_{ts}.json"
    json_path.write_text(
        json.dumps({"summary": summary, "results": results}, indent=2),
        encoding="utf-8",
    )

    # CSV
    csv_lines = [
        f"Run: {ts}",
        f"Total: {summary['total']}, Passed: {summary['passed']}, Failed: {summary['failed']}",
        "",
        "#,prompt,expected,actual,passed,success,action,target,elapsed_ms",
    ]
    for i, r in enumerate(results, 1):
        row = [str(i), _csv(r["prompt"]), _csv(r["expected"]), _csv(r["actual"]),
               str(r["passed"]), str(r["success"]), _csv(r["action"]),
               _csv(r["target"]), str(r["elapsed_ms"])]
        csv_lines.append(",".join(row))
    csv_path = results_dir / f"run_{ts}.csv"
    csv_path.write_text("\n".join(csv_lines), encoding="utf-8")

    # PNG chart
    png_path = results_dir / f"run_{ts}.png"
    _save_metrics_chart(metrics_timeline, summary, png_path)

    return {
        "success": True,
        "results": results,
        "summary": summary,
        "metrics": metrics_timeline,
        "saved_to": {
            "json": str(json_path),
            "csv": str(csv_path),
            "png": str(png_path),
        },
    }


@app.get("/test-mode")
def get_test_mode_status():
    """Return the current test mode state."""
    return {"success": True, "test_mode": get_test_mode()}


@app.post("/test-mode")
def toggle_test_mode(request: ModeRequest):
    """Toggle test mode on or off.

    When test mode is active, skills report what *would* happen without
    performing real side-effects (opening browsers, launching apps).
    """
    enabled = request.mode.lower() in ("on", "true", "1", "enable", "yes")
    new_state = set_test_mode(enabled)
    return {"success": True, "test_mode": new_state}


if __name__ == "__main__":
    import uvicorn

    bus.publish("system_startup", {}, source="api")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
