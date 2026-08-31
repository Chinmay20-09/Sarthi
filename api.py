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
from pathlib import Path

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


def _detect_response_mode(result: dict) -> str:
    """Detect whether a brain-pipeline response was executed deterministically
    or routed to the Hermes conversational layer.

    Returns "command" when the deterministic pipeline handled the request,
    or "hermes" when the NLP fallback skill handled it.
    """
    if result.get("success") and result.get("result"):
        r = result["result"]
        if isinstance(r, dict) and r.get("source") == "nlp":
            return "hermes"
    return "command"


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
            "routing": "hermes",
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
            "routing": "hermes",
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
        "routing": "hermes",
    }


@app.post("/command")
def command(request: CommandRequest):
    """Process a text command through the brain pipeline."""
    # Validate empty input
    if not request.text or not request.text.strip():
        return {
            "action": None,
            "target": None,
            "status": "error",
            "success": False,
            "text": "Please enter a command.",
            "result": None,
            "error": "empty input",
            "input": request.text,
            "mode": get_mode(),
            "routing": "command",
        }

    bus.publish("intent_received", {"text": request.text}, source="api")

    # Mode commands ("conversation mode", "/exit", ...) work in every mode.
    mode_cmd = detect_mode_command(request.text)
    if mode_cmd is not None:
        result = _mode_command_response(request.text, set_mode(mode_cmd))
        result["input"] = request.text
        result["routing"] = "command"
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
    result["routing"] = _detect_response_mode(result)
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
    api_result["routing"] = _detect_response_mode(api_result)

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


def _save_metrics_chart(
    results: list[dict],
    summary: dict,
    hw_history: list[dict],
    hw_summary: dict,
    warnings: dict,
    path: Path,
) -> None:
    """Render a multi-panel dashboard (Pillow) and save as PNG.

    Panels:
      A — Test Results (passed/failed per test)
      B — GPU Temperature (°C)
      C — GPU VRAM (GB)
      D — GPU & CPU Utilization (%)
      Summary — compact dashboard at top
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return  # Pillow not installed — skip silently

    # ── Layout ──
    PANEL_H = 140
    SUMMARY_H = 120
    GAP = 6
    MARGIN = 20
    COL_W = 440
    ROW0_W = 900  # summary spans full width
    TOTAL_W = ROW0_W
    n_panels = 4
    PANELS_PER_ROW = 2
    n_rows = (n_panels + PANELS_PER_ROW - 1) // PANELS_PER_ROW
    TOTAL_H = SUMMARY_H + GAP + n_rows * (PANEL_H + GAP) + MARGIN

    BG = (14, 14, 14)
    PANEL_BG = (20, 22, 26)
    GRID = (35, 38, 42)
    TEXT = (187, 201, 206)
    TEXT_DIM = (100, 110, 120)
    CYAN = (0, 217, 255)
    RED = (255, 107, 107)
    GREEN = (80, 220, 130)
    ORANGE = (255, 183, 125)
    PURPLE = (174, 130, 255)
    YELLOW = (255, 220, 80)

    img = Image.new("RGB", (TOTAL_W, TOTAL_H), BG)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("consola.ttf", 11)
        font_sm = ImageFont.truetype("consola.ttf", 9)
        font_lg = ImageFont.truetype("consola.ttf", 14)
        font_title = ImageFont.truetype("consola.ttf", 12)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font
        font_lg = font
        font_title = font

    # ── Summary dashboard ──
    sy = 8
    draw.text((TOTAL_W // 2, sy), "SARTHI TEST DASHBOARD", fill=CYAN, font=font_lg, anchor="mt")
    sy += 20

    # Three columns: Test Suite | GPU | CPU
    col_w = TOTAL_W // 3
    cx1 = MARGIN + 10
    cx2 = MARGIN + col_w + 10
    cx3 = MARGIN + 2 * col_w + 10

    # Test Suite column
    draw.text((cx1, sy), "TEST SUITE", fill=TEXT, font=font_title)
    sy_ts = sy + 16
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    pass_rate = (passed / total * 100) if total > 0 else 0
    avg_lat = summary.get("avg_latency_ms", 0)
    max_lat = summary.get("max_latency_ms", 0)
    draw.text((cx1, sy_ts), f"Total: {total}", fill=TEXT, font=font_sm)
    draw.text((cx1, sy_ts + 12), f"Passed: {passed}", fill=GREEN, font=font_sm)
    draw.text((cx1, sy_ts + 24), f"Failed: {failed}", fill=RED, font=font_sm)
    draw.text((cx1, sy_ts + 36), f"Pass rate: {pass_rate:.1f}%", fill=CYAN, font=font_sm)
    draw.text((cx1, sy_ts + 48), f"Avg latency: {avg_lat:.0f}ms", fill=TEXT, font=font_sm)
    draw.text((cx1, sy_ts + 60), f"Max latency: {max_lat:.0f}ms", fill=ORANGE, font=font_sm)

    # GPU column
    draw.text((cx2, sy), "GPU", fill=TEXT, font=font_title)
    sy_gpu = sy + 16
    gpu_temp = hw_summary.get("gpu_temperature", {})
    gpu_vram = hw_summary.get("gpu_vram", {})
    gpu_util = hw_summary.get("gpu_utilization", {})
    gt_cur = gpu_temp.get("current")
    gt_max = gpu_temp.get("max")
    gt_avg = gpu_temp.get("avg")
    gv_cur = gpu_vram.get("current")
    gv_peak = gpu_vram.get("peak")
    gv_total = gpu_vram.get("total")
    gu_avg = gpu_util.get("avg")
    gu_peak = gpu_util.get("peak")
    draw.text(
        (cx2, sy_gpu),
        f"Temp: {_fmt(gt_cur)} / max {_fmt(gt_max)} / avg {_fmt(gt_avg)} °C",
        fill=ORANGE,
        font=font_sm,
    )
    draw.text(
        (cx2, sy_gpu + 12),
        f"VRAM: {_fmt(gv_cur)} / peak {_fmt(gv_peak)} / total {_fmt(gv_total)} GB",
        fill=PURPLE,
        font=font_sm,
    )
    draw.text(
        (cx2, sy_gpu + 24),
        f"Util: avg {_fmt(gu_avg)} / peak {_fmt(gu_peak)} %",
        fill=CYAN,
        font=font_sm,
    )
    # Warnings
    wy = sy_gpu + 40
    for wtype, wdata in warnings.items():
        level = wdata.get("level", "warning")
        color = RED if level == "critical" else YELLOW
        msg = f"⚠ {wtype}: {level.upper()}"
        draw.text((cx2, wy), msg, fill=color, font=font_sm)
        wy += 12
    if not warnings:
        draw.text((cx2, wy), "No sustained warnings", fill=GREEN, font=font_sm)

    # CPU column
    draw.text((cx3, sy), "CPU", fill=TEXT, font=font_title)
    sy_cpu = sy + 16
    cpu_util = hw_summary.get("cpu_utilization", {})
    cu_avg = cpu_util.get("avg")
    cu_peak = cpu_util.get("peak")
    draw.text(
        (cx3, sy_cpu),
        f"Util: avg {_fmt(cu_avg)} / peak {_fmt(cu_peak)} %",
        fill=PURPLE,
        font=font_sm,
    )
    cpu_temp = hw_summary.get("cpu_temperature", {})
    ct_cur = cpu_temp.get("current")
    ct_max = cpu_temp.get("max")
    if ct_cur is not None:
        draw.text(
            (cx3, sy_cpu + 12),
            f"Temp: {_fmt(ct_cur)} / max {_fmt(ct_max)} °C",
            fill=ORANGE,
            font=font_sm,
        )
    else:
        draw.text((cx3, sy_cpu + 12), "CPU temp: unavailable", fill=TEXT_DIM, font=font_sm)

    # ── Panel positions ──
    panel_defs = [
        ("A", "TEST RESULTS", CYAN),
        ("B", "GPU TEMPERATURE", ORANGE),
        ("C", "GPU VRAM", PURPLE),
        ("D", "GPU & CPU UTILIZATION", CYAN),
    ]
    panel_y_start = SUMMARY_H + GAP

    for pi, (pid, title, color) in enumerate(panel_defs):
        row = pi // PANELS_PER_ROW
        col = pi % PANELS_PER_ROW
        px = MARGIN + col * (COL_W + GAP)
        py = panel_y_start + row * (PANEL_H + GAP)
        pw = COL_W
        ph = PANEL_H

        # Panel background
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=4, fill=PANEL_BG)
        # Title bar
        draw.rectangle([px, py, px + pw, py + 18], fill=(28, 32, 38))
        draw.text((px + 6, py + 3), f"{pid} — {title}", fill=color, font=font_title)

        # Plot area
        plot_x = px + 50
        plot_y = py + 22
        plot_w = pw - 70
        plot_h = ph - 34

        if len(results) < 2:
            draw.text(
                (px + pw // 2, py + ph // 2),
                "Insufficient data",
                fill=TEXT_DIM,
                font=font_sm,
                anchor="mm",
            )
            continue

        # Grid lines
        for gi in range(5):
            gy = plot_y + int(plot_h * gi / 4)
            draw.line([(plot_x, gy), (plot_x + plot_w, gy)], fill=GRID, width=1)

        x_step = plot_w / (len(results) - 1)
        dense = len(results) > 20
        dot_r = 2 if dense else 3

        if pid == "A":
            # ── Panel A: Test Results (passed/failed per test) ──
            for i, r in enumerate(results):
                cx = plot_x + int(i * x_step)
                bar_w = max(2, int(min(x_step * 0.35, 10)))
                if r.get("passed"):
                    draw.rectangle(
                        [cx - bar_w, plot_y + plot_h - 8, cx, plot_y + plot_h],
                        fill=GREEN,
                        outline=GREEN,
                    )
                else:
                    draw.rectangle(
                        [cx - bar_w, plot_y + plot_h - 8, cx, plot_y + plot_h],
                        fill=RED,
                        outline=RED,
                    )
            # Failure type color coding below the bars
            failure_colors = {
                "pass": GREEN,
                "executor_unsupported_action": RED,
                "app_not_found": ORANGE,
                "entity_resolution": PURPLE,
                "no_target": YELLOW,
                "conversational_nlp": TEXT_DIM,
                "execution_error": RED,
            }
            for i, r in enumerate(results):
                cx = plot_x + int(i * x_step)
                ft = r.get("failure_type", "pass")
                fc = failure_colors.get(ft, TEXT_DIM)
                draw.rectangle(
                    [cx - bar_w, plot_y + plot_h - 16, cx, plot_y + plot_h - 9],
                    fill=fc,
                )
            # Legend for panel A
            leg_x = plot_x + 2
            leg_y = plot_y + 2
            for label, c in [
                ("Passed", GREEN),
                ("Failed", RED),
                ("App not found", ORANGE),
                ("Unsupported action", RED),
                ("Entity resolution", PURPLE),
            ]:
                draw.rectangle([leg_x, leg_y, leg_x + 6, leg_y + 6], fill=c)
                draw.text((leg_x + 8, leg_y - 1), label, fill=TEXT_DIM, font=font_sm)
                leg_x += len(label) * 5 + 20
                if leg_x > plot_x + plot_w - 50:
                    leg_x = plot_x + 2
                    leg_y += 10

            # Y-axis: 0 / total
            draw.text((plot_x - 6, plot_y + plot_h - 6), "0", fill=TEXT, font=font_sm, anchor="rm")
            draw.text((plot_x - 6, plot_y + 2), str(total), fill=TEXT, font=font_sm, anchor="rm")

        elif pid == "B":
            # ── Panel B: GPU Temperature ──
            temps = [r.get("gpu_temperature_c") for r in hw_history]
            valid_temps = [t for t in temps if t is not None]
            if valid_temps:
                max_t = max(valid_temps) * 1.2 or 100
                points = []
                for i, t in enumerate(temps):
                    if t is None:
                        continue
                    x = plot_x + int(i * x_step)
                    y = plot_y + plot_h - int((t / max_t) * plot_h)
                    points.append((x, y))
                if len(points) > 1:
                    draw.line(points, fill=ORANGE, width=2)
                for x, y in points:
                    draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r], fill=ORANGE)
                draw.text(
                    (plot_x - 6, plot_y + 2), f"{max_t:.0f}", fill=ORANGE, font=font_sm, anchor="rm"
                )
                draw.text(
                    (plot_x - 6, plot_y + plot_h - 6), "0", fill=ORANGE, font=font_sm, anchor="rm"
                )
                draw.text((plot_x + plot_w + 4, plot_y + 2), "°C", fill=ORANGE, font=font_sm)
            else:
                draw.text(
                    (px + pw // 2, py + ph // 2),
                    "GPU temp unavailable",
                    fill=TEXT_DIM,
                    font=font_sm,
                    anchor="mm",
                )

        elif pid == "C":
            # ── Panel C: GPU VRAM ──
            vrams = [r.get("gpu_vram_used_gb") for r in hw_history]
            valid_vrams = [v for v in vrams if v is not None]
            vram_total = hw_summary.get("gpu_vram", {}).get("total")
            if valid_vrams:
                max_v = max(valid_vrams) * 1.2 or 1.0
                if vram_total and vram_total > max_v:
                    max_v = vram_total * 1.1
                # VRAM total reference line
                if vram_total and vram_total > 0:
                    ty = plot_y + plot_h - int((vram_total / max_v) * plot_h)
                    draw.line([(plot_x, ty), (plot_x + plot_w, ty)], fill=TEXT_DIM, width=1)
                    draw.text(
                        (plot_x + plot_w + 4, ty - 5),
                        f"{vram_total:.1f} GB",
                        fill=TEXT_DIM,
                        font=font_sm,
                    )
                points = []
                for i, v in enumerate(vrams):
                    if v is None:
                        continue
                    x = plot_x + int(i * x_step)
                    y = plot_y + plot_h - int((v / max_v) * plot_h)
                    points.append((x, y))
                if len(points) > 1:
                    draw.line(points, fill=PURPLE, width=2)
                for x, y in points:
                    draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r], fill=PURPLE)
                draw.text(
                    (plot_x - 6, plot_y + 2), f"{max_v:.1f}", fill=PURPLE, font=font_sm, anchor="rm"
                )
                draw.text(
                    (plot_x - 6, plot_y + plot_h - 6), "0", fill=PURPLE, font=font_sm, anchor="rm"
                )
                draw.text((plot_x + plot_w + 4, plot_y + 2), "GB", fill=PURPLE, font=font_sm)
            else:
                draw.text(
                    (px + pw // 2, py + ph // 2),
                    "GPU VRAM unavailable",
                    fill=TEXT_DIM,
                    font=font_sm,
                    anchor="mm",
                )

        elif pid == "D":
            # ── Panel D: GPU & CPU Utilization ──
            gpu_utils = [r.get("gpu_utilization_percent") or 0 for r in hw_history]
            cpu_utils = [r.get("cpu_utilization_percent") or 0 for r in hw_history]
            # GPU line
            points_gpu = []
            for i, g in enumerate(gpu_utils):
                x = plot_x + int(i * x_step)
                y = plot_y + plot_h - int((g / 100) * plot_h)
                points_gpu.append((x, y))
            if len(points_gpu) > 1:
                draw.line(points_gpu, fill=CYAN, width=2)
            for x, y in points_gpu:
                draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r], fill=CYAN)
            # CPU line
            points_cpu = []
            for i, c in enumerate(cpu_utils):
                x = plot_x + int(i * x_step)
                y = plot_y + plot_h - int((c / 100) * plot_h)
                points_cpu.append((x, y))
            if len(points_cpu) > 1:
                draw.line(points_cpu, fill=PURPLE, width=1)
            for x, y in points_cpu:
                draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=PURPLE)
            # Y-axis
            draw.text((plot_x - 6, plot_y + plot_h - 6), "0%", fill=TEXT, font=font_sm, anchor="rm")
            draw.text((plot_x - 6, plot_y + 2), "100%", fill=TEXT, font=font_sm, anchor="rm")
            # Legend
            draw.rectangle([plot_x + 2, plot_y + 2, plot_x + 8, plot_y + 8], fill=CYAN)
            draw.text((plot_x + 10, plot_y + 1), "GPU", fill=CYAN, font=font_sm)
            draw.rectangle([plot_x + 52, plot_y + 2, plot_x + 58, plot_y + 8], fill=PURPLE)
            draw.text((plot_x + 60, plot_y + 1), "CPU", fill=PURPLE, font=font_sm)

        # X-axis labels (every Nth test)
        label_step = max(1, len(results) // 8)
        for i in range(0, len(results), label_step):
            x = plot_x + int(i * x_step)
            draw.text(
                (x, plot_y + plot_h + 3), f"#{i + 1}", fill=TEXT_DIM, font=font_sm, anchor="mt"
            )
        # Always show last
        if len(results) > 1:
            x = plot_x + int((len(results) - 1) * x_step)
            draw.text(
                (x, plot_y + plot_h + 3),
                f"#{len(results)}",
                fill=TEXT_DIM,
                font=font_sm,
                anchor="mt",
            )

    img.save(str(path))


def _fmt(val) -> str:
    """Format a numeric value for dashboard display, or return 'N/A'."""
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.1f}"
    return str(val)


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

    Captures per-test hardware telemetry, classifies failure types,
    and generates a multi-panel dashboard.
    """
    import json
    import time
    from pathlib import Path

    from utils.telemetry import HardwareThresholds, TelemetryCollector, classify_failure

    path = Path(__file__).parent / "test_prompts.json"
    if not path.exists():
        return {"success": False, "error": "test_prompts.json not found"}

    try:
        prompts = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"success": False, "error": str(exc)}

    if not prompts:
        return {"success": True, "results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}

    tc = TelemetryCollector()
    hw_history: list[dict] = []
    hw_summary: dict = {}
    warnings: dict = {}
    vram_total_suite: float | None = None

    # Enable test mode so skills report what would happen without side-effects
    was_test = get_test_mode()
    set_test_mode(True)

    # Start periodic background sampling (lightweight, 2s interval)
    tc.start_periodic_sampling(interval_seconds=2.0)

    try:
        results = []
        for idx, entry in enumerate(prompts):
            prompt_text = entry.get("prompt", "")
            expected = entry.get("expected", "")
            category = entry.get("category", "")

            # 1) Capture baseline hardware snapshot
            baseline = tc.snapshot()

            # 2) Execute the test
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
                result_record = {
                    "prompt": prompt_text,
                    "expected": expected,
                    "actual": actual,
                    "success": response.success,
                    "passed": passed,
                    "action": api.get("action", ""),
                    "target": api.get("target", ""),
                    "elapsed_ms": elapsed_ms,
                    "category": category,
                }
            except Exception as exc:
                elapsed_ms = round((time.time() - start) * 1000)
                result_record = {
                    "prompt": prompt_text,
                    "expected": expected,
                    "actual": str(exc),
                    "success": False,
                    "passed": False,
                    "action": "",
                    "target": "",
                    "elapsed_ms": elapsed_ms,
                    "category": category,
                }

            # 3) Capture post-test hardware snapshot
            post = tc.snapshot()

            # 4) Build per-test hardware record
            hw_record = tc.build_test_record(baseline, post)
            hw_history.append(hw_record)
            result_record["failure_type"] = classify_failure(result_record)

            # Track VRAM total across suite
            if hw_record.get("gpu_vram_total_gb") is not None and vram_total_suite is None:
                vram_total_suite = hw_record["gpu_vram_total_gb"]

            results.append(result_record)
    finally:
        tc.stop_periodic_sampling()
        set_test_mode(was_test)

    # Compute suite-level hardware summary
    hw_summary = tc.suite_summary()
    if vram_total_suite is not None:
        hw_summary.setdefault("gpu_vram", {})["total"] = vram_total_suite

    # Check for sustained hardware warnings
    thresholds = HardwareThresholds()
    # No hardcoded thresholds — display values without alarming if none configured
    warnings = thresholds.check(hw_history)

    # Test summary with latency stats
    latencies = [r["elapsed_ms"] for r in results]
    passed_count = sum(1 for r in results if r["passed"])
    summary = {
        "total": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "pass_rate": round(passed_count / max(len(results), 1) * 100, 1),
        "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1),
        "max_latency_ms": max(latencies) if latencies else 0,
    }

    # Category breakdown
    categories: dict[str, dict] = {}
    for r in results:
        cat = r.get("category", "")
        if not cat:
            continue
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0, "failed": 0}
        categories[cat]["total"] += 1
        if r.get("passed"):
            categories[cat]["passed"] += 1
        else:
            categories[cat]["failed"] += 1
    summary["categories"] = categories

    # Failure type breakdown
    failure_types: dict[str, int] = {}
    for r in results:
        ft = r.get("failure_type", "unknown")
        failure_types[ft] = failure_types.get(ft, 0) + 1
    summary["failure_types"] = failure_types

    # Auto-save results to results/ directory (JSON + CSV)
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    _cleanup_old_results(results_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON
    json_path = results_dir / f"run_{ts}.json"
    json_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "results": results,
                "hardware": hw_history,
                "hw_summary": hw_summary,
                "warnings": warnings,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    # CSV with hardware columns
    csv_header = (
        "test_index,timestamp,prompt,expected,actual,passed,success,"
        "action,target,elapsed_ms,category,failure_type,"
        "gpu_temperature_c,gpu_vram_used_gb,gpu_vram_total_gb,"
        "gpu_utilization_percent,cpu_utilization_percent,"
        "gpu_power_watts,cpu_temperature_c,ram_used_gb,ram_total_gb"
    )
    csv_lines = [
        f"Run: {ts}",
        f"Total: {summary['total']}, Passed: {summary['passed']}, Failed: {summary['failed']}",
        f"Pass rate: {summary['pass_rate']}%, Avg latency: {summary['avg_latency_ms']}ms, Max latency: {summary['max_latency_ms']}ms",
        "",
        csv_header,
    ]
    for i, (r, hw) in enumerate(zip(results, hw_history), 1):
        row = [
            str(i),
            hw.get("timestamp", ""),
            _csv(r["prompt"]),
            _csv(r["expected"]),
            _csv(r["actual"]),
            str(r["passed"]),
            str(r["success"]),
            _csv(r["action"]),
            _csv(r["target"]),
            str(r["elapsed_ms"]),
            _csv(r.get("category", "")),
            _csv(r.get("failure_type", "")),
            str(hw.get("gpu_temperature_c", "")),
            str(hw.get("gpu_vram_used_gb", "")),
            str(hw.get("gpu_vram_total_gb", "")),
            str(hw.get("gpu_utilization_percent", "")),
            str(hw.get("cpu_utilization_percent", "")),
            str(hw.get("gpu_power_watts", "")),
            str(hw.get("cpu_temperature_c", "")),
            str(hw.get("ram_used_gb", "")),
            str(hw.get("ram_total_gb", "")),
        ]
        csv_lines.append(",".join(row))
    csv_path = results_dir / f"run_{ts}.csv"
    csv_path.write_text("\n".join(csv_lines), encoding="utf-8")

    # PNG multi-panel dashboard
    png_path = results_dir / f"run_{ts}.png"
    _save_metrics_chart(results, summary, hw_history, hw_summary, warnings, png_path)

    return {
        "success": True,
        "results": results,
        "summary": summary,
        "hardware": hw_history,
        "hw_summary": hw_summary,
        "warnings": warnings,
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
