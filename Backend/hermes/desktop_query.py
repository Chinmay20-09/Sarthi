"""Focused model-to-Desktop-Hand query flow for the Windows client."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from hands.desktop.capabilities import action_spec
from hands.local import get_desktop_hand
from skills.browser.youtube import get_first_youtube_video_url

from hermes.conversation import DEFAULT_SESSION, get_conversation_store
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.service import get_orchestrator
from hermes.tool_planner import parse_tool_call

logger = logging.getLogger(__name__)

# Keep model-selectable actions narrow. These names and argument rules come
# from implemented Hand capabilities; open_url is forwarded to the GUI so it
# opens on the user's desktop rather than in the backend process.
DESKTOP_ACTIONS: dict[str, tuple[str, str]] = {
    "desktop_get_active_window": (
        "get_active_window",
        "Read the foreground window title and details.",
    ),
    "desktop_list_windows": ("list_windows", "List currently open windows."),
    "desktop_open_url": ("open_url", "Open an explicit http or https URL in the default browser."),
    "desktop_type_text": ("type_text", "Type the exact text supplied into the foreground window."),
    "desktop_press_key": ("press_key", "Press one explicit key in the foreground window."),
    "desktop_hotkey": ("hotkey", "Press an explicit list of keys as a hotkey."),
}

# These narrowly scoped UI actions are returned to the desktop client for
# execution there. They never run in the backend process.
CLIENT_ACTION_STATES = ("sleeping", "happy", "thinking", "working", "confused", "sad")
# Match direct pet-state requests locally in the backend. These states are
# backed by the Windows client's Hitori image map (confused reuses sad).
_PET_STATE_ALIASES = {
    "sleeping": {"sleeping", "sleep", "asleep"},
    "happy": {"happy", "happiness", "cheerful"},
    "thinking": {"thinking", "think", "thoughtful"},
    "working": {"working", "work", "focused"},
    "confused": {"confused", "confusion"},
    "sad": {"sad", "sadness", "unhappy"},
}
_PET_COMMAND_VERBS = {"turn", "make", "set", "change", "switch"}


def _tool_descriptors() -> list[dict[str, Any]]:
    """Return schemas for the actions, derived from the Hand capability map."""
    result = []
    for tool_name, (action, description) in DESKTOP_ACTIONS.items():
        spec = action_spec(action)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, rule in spec.items():
            rule_kind, rule_value = rule if isinstance(rule, tuple) else ("required", Any)
            if rule_kind == "optional":
                continue
            python_type = rule_value if rule_kind == "required" else Any
            type_name = "array" if python_type is list else "string"
            properties[name] = {"type": type_name}
            if python_type is list:
                properties[name]["items"] = {"type": "string"}
            required.append(name)
        result.append(
            {
                "name": tool_name,
                "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            }
        )
    result.append(
        {
            "name": "desktop_set_pet_state",
            "description": "Change the Sarthi desktop pet image to a supported state.",
            "parameters": {
                "type": "object",
                "properties": {"state": {"type": "string", "enum": list(CLIENT_ACTION_STATES)}},
                "required": ["state"],
            },
        }
    )
    return result


def _validate_action(action: str, arguments: Any) -> str | None:
    """Strictly validate a model action before handing it to DesktopHand."""
    if action not in {item[0] for item in DESKTOP_ACTIONS.values()}:
        return "The requested desktop action is not supported."
    if not isinstance(arguments, dict):
        return "Desktop action arguments must be an object."
    spec = action_spec(action)
    unknown = set(arguments) - set(spec)
    if unknown:
        return f"Unsupported argument: {sorted(unknown)[0]}"
    for name, rule in spec.items():
        if name not in arguments:
            if isinstance(rule, tuple) and rule[0] == "optional":
                continue
            return f"Missing required argument: {name}"
        value = arguments[name]
        expected = rule[1] if isinstance(rule, tuple) else Any
        if expected is Any:
            continue
        valid = (
            isinstance(value, expected)
            if isinstance(expected, type)
            else isinstance(value, expected)
        )
        if expected is int and isinstance(value, bool):
            valid = False
        if not valid:
            return f"Argument '{name}' has the wrong type."
        if expected is list and (
            not value or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            return f"Argument '{name}' must be a non-empty list of strings."
        if isinstance(value, str) and not value.strip():
            return f"Argument '{name}' must not be empty."
        if action == "open_url" and name == "url":
            if len(value) > 2048:
                return "Argument 'url' is too long."
            try:
                parsed = urlsplit(value)
            except ValueError:
                return "Argument 'url' is malformed."
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                return "Only valid HTTP or HTTPS URLs are supported."
    return None


def _action_failure(trace: list[dict], tool: str, error: str, *, invalid: bool = False) -> dict:
    return {
        "success": False,
        "response": error,
        "error": "invalid_action" if invalid else "desktop_action_failed",
        "action": {"name": tool, "success": False, "message": error},
        "trace": trace,
    }


def _validate_pet_state(arguments: Any) -> str | None:
    if not isinstance(arguments, dict) or set(arguments) != {"state"}:
        return "Pet action requires exactly one 'state' argument."
    state = arguments.get("state")
    if not isinstance(state, str) or state not in CLIENT_ACTION_STATES:
        return "Unsupported pet state. Choose a supported desktop pet state."
    return None


def _desktop_shortcut(query: str) -> dict[str, Any] | None:
    """Resolve deterministic desktop commands before invoking the model."""
    words = re.sub(r"[^a-z0-9]+", " ", query.lower()).split()
    youtube_verb = re.search(r"\b(play|watch|search)\b", query, re.IGNORECASE)
    if youtube_verb and ("youtube" in words or words[0] in {"play", "watch"}):
        title = query[youtube_verb.end() :]
        title = re.sub(r"\b(on|in)\s+youtube\b.*$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"^\s+(on|in)\s+youtube\b.*$", "", title, flags=re.IGNORECASE)
        title = title.strip(" \t.,!?\"'")
        if title.lower() == "youtube":
            title = ""
        url = "https://www.youtube.com/"
        if title:
            url = (
                get_first_youtube_video_url(title)
                if youtube_verb.group(1).lower() in {"play", "watch"}
                else None
            ) or ("https://www.youtube.com/results?" + urlencode({"search_query": title}))
        return {
            "tool": "desktop_open_url",
            "arguments": {"url": url},
        }
    if "youtube" in words and {"open", "launch"}.intersection(words):
        return {"tool": "desktop_open_url", "arguments": {"url": "https://www.youtube.com/"}}
    command_words = words[1:] if words and words[0] in {"please", "hitori", "pet"} else words
    if command_words and command_words[0] in _PET_COMMAND_VERBS:
        requested = set(command_words)
        for state, aliases in _PET_STATE_ALIASES.items():
            if requested.intersection(aliases):
                return {
                    "tool": "desktop_set_pet_state",
                    "arguments": {"state": state},
                }
    return None


def _is_compound_desktop_request(query: str) -> bool:
    """Only spend a model call on decomposition when the request has multiple commands."""
    words = re.sub(r"[^a-z0-9]+", " ", query.lower()).split()
    has_joiner = "and" in words or "then" in words
    has_pet_command = bool(_PET_COMMAND_VERBS.intersection(words)) and any(
        aliases.intersection(words) for aliases in _PET_STATE_ALIASES.values()
    )
    has_youtube_command = "youtube" in words and bool(
        {"play", "watch", "search", "open", "launch"}.intersection(words)
    )
    return has_joiner and has_pet_command and has_youtube_command


def _resolve_decomposed_subtask(query: str) -> dict[str, Any] | None:
    """Accept only complete commands in the deterministic Phase One allowlist."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", query.lower()).split())
    pet_match = re.fullmatch(
        r"(?:please )?(?:turn|make|set|change|switch) "
        r"(?:(?:the )?(?:pet|hitori|emotion|mood) (?:to|into) )?([a-z]+)",
        normalized,
    )
    if pet_match:
        requested = pet_match.group(1)
        for state, aliases in _PET_STATE_ALIASES.items():
            if requested in aliases:
                return {
                    "tool": "desktop_set_pet_state",
                    "arguments": {"state": state},
                }
    youtube_match = re.fullmatch(
        r"(?:please )?(?:play|watch|search) (.+?) (?:on|in) youtube", normalized
    )
    if youtube_match:
        title = youtube_match.group(1).removeprefix("song ").removeprefix("video ").strip()
        if title:
            video_url = get_first_youtube_video_url(title)
            return {
                "tool": "desktop_open_url",
                "arguments": {
                    "url": video_url
                    or "https://www.youtube.com/results?" + urlencode({"search_query": title})
                },
            }
    if normalized in {"play youtube", "open youtube", "launch youtube"}:
        return {"tool": "desktop_open_url", "arguments": {"url": "https://www.youtube.com/"}}
    return None


def _decompose_desktop_request(query: str, task: Task) -> tuple[list[dict[str, Any]] | None, dict | None]:
    """Ask Hermes only to split a compound request into deterministic subcommands."""
    orchestrator = get_orchestrator()
    decomposition_task = Task(
        id=task.id,
        prompt=query,
        task_type="desktop_decomposition",
        instructions=(
            "Split the user's compound Windows desktop request into 2 to 5 ordered, standalone "
            "subcommands that preserve the requested order. Return only JSON in this exact shape: "
            '{"tasks":["turn sad","play lost in love on youtube"]}. Do not answer, choose tools, '
            "or include unsupported work. Each subcommand must be a direct pet-state command or a "
            "YouTube play/search command."
        ),
        history=task.history,
    )
    result = orchestrator.generate(decomposition_task)
    if not result.success:
        return None, {
            "success": False,
            "response": result.error or "The language model could not split that request.",
            "error": "model_unavailable",
            "action": None,
            "trace": [],
        }
    try:
        payload = json.loads(result.text)
    except (TypeError, json.JSONDecodeError):
        payload = None
    subtasks = payload.get("tasks") if isinstance(payload, dict) else None
    if (
        not isinstance(subtasks, list)
        or not 2 <= len(subtasks) <= 5
        or any(not isinstance(item, str) or not item.strip() or len(item) > 500 for item in subtasks)
    ):
        return None, {
            "success": False,
            "response": "The model returned an invalid task breakdown. Try phrasing the actions separately.",
            "error": "invalid_decomposition",
            "action": None,
            "trace": [],
        }
    actions = []
    for subtask in subtasks:
        action = _resolve_decomposed_subtask(subtask)
        if action is None:
            return None, {
                "success": False,
                "response": "The task breakdown included an unsupported desktop action.",
                "error": "unsupported_subtask",
                "action": None,
                "trace": [],
            }
        actions.append(action)
    return actions, {"provider": result.provider, "model": result.model}


def run_desktop_query(query: str, session_id: str | None = None) -> dict[str, Any]:
    """Ask the configured provider, optionally run one validated Hand action."""
    query = query.strip()
    session_id = session_id or DEFAULT_SESSION
    trace: list[dict[str, Any]] = []
    try:
        store = get_conversation_store()
        try:
            history = store.get_history(session_id)
        except Exception as exc:
            logger.warning("desktop query: conversation history unavailable: %s", exc)
            history = []
        tools = _tool_descriptors()
        instructions = (
            "You are Sarthi, a helpful Windows desktop assistant. Answer ordinary questions directly. "
            "Use at most one listed desktop action when needed. Never invent actions or arguments. "
            "Only request an action when the user clearly asked for that interaction. If an action is needed, "
            'reply only as {"tool_call":{"tool":"<listed name>","arguments":{...}}}. '
            "For 'turn sad' or similar mood requests, use desktop_set_pet_state. For 'play YouTube', "
            "open https://www.youtube.com/ using desktop_open_url. Do not claim an action is complete before "
            "receiving its result. For ordinary questions, reply in plain text.\n\n"
            "Available tools:\n"
            + "\n".join(
                f"- {tool['name']}: {tool['description']} Arguments: {tool['parameters']['properties']}"
                for tool in tools
            )
        )
        orchestrator: HermesOrchestrator | None = None
        task = Task(
            id=f"desktop_{uuid4().hex[:10]}",
            prompt=query,
            task_type="desktop_query",
            instructions=instructions,
            history=history,
        )
        if _is_compound_desktop_request(query):
            subtasks, model_info = _decompose_desktop_request(query, task)
            if model_info and model_info.get("success") is False:
                model_info["trace"] = [{"step": "model_decomposition", "success": False}]
                model_info["session_id"] = session_id
                return model_info
            if subtasks is None:
                raise RuntimeError("compound request decomposition failed")
            client_actions = [
                (
                    {"type": "set_pet_state", "state": item["arguments"]["state"]}
                    if item["tool"] == "desktop_set_pet_state"
                    else {"type": "open_url", "url": item["arguments"]["url"]}
                )
                for item in subtasks
            ]
            descriptions = [
                (
                    f"The desktop pet will change to {action['state']}."
                    if action["type"] == "set_pet_state"
                    else f"The desktop client will open {action['url']}."
                )
                for action in client_actions
            ]
            response = f"Queued {len(client_actions)} desktop actions: " + "; ".join(descriptions)
            result = {
                "success": True,
                "response": response,
                "error": None,
                "action": {"name": "desktop_sequence", "success": True, "pending": True},
                "client_actions": client_actions,
                "provider": model_info.get("provider", "") if model_info else "",
                "model": model_info.get("model", "") if model_info else "",
                "trace": [
                    {"step": "model_decomposition", "task_count": len(subtasks)},
                    {"step": "client_actions_queued", "count": len(client_actions)},
                ],
                "session_id": session_id,
            }
            try:
                store.add_turn(session_id, "user", query)
                store.add_turn(session_id, "assistant", response)
            except Exception as exc:
                logger.warning("desktop query: conversation history could not be saved: %s", exc)
            return result
        call = _desktop_shortcut(query)
        decision = None
        if call:
            trace.append({"step": "desktop_shortcut", "tool": call["tool"]})
        else:
            orchestrator = get_orchestrator()
            decision = orchestrator.generate(task)
            if not decision.success:
                return {
                    "success": False,
                    "response": decision.error or "The language model is unavailable.",
                    "error": "model_unavailable",
                    "action": None,
                    "trace": trace,
                }
            trace.append(
                {"step": "model_decision", "provider": decision.provider, "model": decision.model}
            )
            call = parse_tool_call(decision.text)
        if call is None:
            response = decision.text.strip()
            if not response:
                return {
                    "success": False,
                    "response": "The language model returned an empty response.",
                    "error": "empty_model_response",
                    "action": None,
                    "trace": trace,
                }
            result = {
                "success": True,
                "response": response,
                "error": None,
                "action": None,
                "provider": decision.provider if decision else "Sarthi",
                "model": decision.model if decision else "",
                "trace": trace,
            }
        else:
            tool_name = call["tool"]
            client_action = None
            if tool_name == "desktop_set_pet_state":
                invalid = _validate_pet_state(call.get("arguments"))
                if invalid:
                    return _action_failure(trace, "set_pet_state", invalid, invalid=True)
                state = call["arguments"]["state"]
                client_action = {"type": "set_pet_state", "state": state}
                action = "set_pet_state"
                status = {
                    "name": action,
                    "success": True,
                    "pending": True,
                    "message": f"The desktop pet will change to {state}.",
                    "data": {},
                }
            else:
                action_pair = DESKTOP_ACTIONS.get(tool_name)
                if action_pair is None:
                    return _action_failure(
                        trace,
                        tool_name,
                        "The requested desktop action is not supported.",
                        invalid=True,
                    )
                action, _ = action_pair
                invalid = _validate_action(action, call.get("arguments"))
                if invalid:
                    return _action_failure(trace, action, invalid, invalid=True)
                if action == "open_url":
                    url = call["arguments"]["url"]
                    client_action = {"type": "open_url", "url": url}
                    status = {
                        "name": action,
                        "success": True,
                        "pending": True,
                        "message": f"The desktop client will open {url}.",
                        "data": {},
                    }
                else:
                    hand_result = get_desktop_hand().execute(action, **call["arguments"])
                    trace.append(
                        {
                            "step": "desktop_action",
                            "action": action,
                            "success": bool(hand_result.get("success")),
                        }
                    )
                    status = {
                        "name": action,
                        "success": bool(hand_result.get("success")),
                        "message": str(hand_result.get("message") or ""),
                        "data": hand_result.get("data") or {},
                    }
                    if not status["success"]:
                        return _action_failure(
                            trace, action, status["message"] or "The desktop action failed."
                        )

            if client_action:
                trace.append({"step": "client_action_queued", "action": client_action["type"]})
            # The two exact first-run shortcuts need no model round-trip to
            # act. Other model-selected actions get a model-written response.
            if client_action and decision is None:
                response = status["message"] or "The desktop action was queued."
                final = None
            else:
                followup_rules = (
                    "This action is queued for the desktop client and has not executed yet. "
                    "Use future or present-progressive wording; do not claim it succeeded."
                    if client_action
                    else "Describe the confirmed Desktop Hand result. Do not claim anything beyond it."
                )
                if orchestrator is None:
                    orchestrator = get_orchestrator()
                followup = Task(
                    id=task.id,
                    prompt=query,
                    task_type="desktop_query",
                    instructions=(
                        "Write a concise user-facing response. "
                        + followup_rules
                        + "\nConfirmed or queued action: "
                        + str(status)
                    ),
                    history=history,
                )
                try:
                    final = orchestrator.generate(followup)
                except Exception:
                    final = None
                if final is None or not final.success or not final.text.strip():
                    response = status["message"] or "The desktop action was queued."
                else:
                    response = final.text.strip()
            result = {
                "success": True,
                "response": response,
                "error": None,
                "action": status,
                "client_action": client_action,
                "provider": final.provider
                if final
                else decision.provider
                if decision
                else "Sarthi",
                "model": final.model if final else decision.model if decision else "",
                "trace": trace,
            }
        try:
            store.add_turn(session_id, "user", query)
            if result["success"]:
                store.add_turn(session_id, "assistant", result["response"])
        except Exception as exc:
            # A database write failure must not change the reported outcome of
            # a desktop action that has already completed.
            logger.warning("desktop query: conversation history could not be saved: %s", exc)
        result["session_id"] = session_id
        return result
    except Exception:
        # Provider, conversation store, or hand integration errors must not
        # escape the HTTP request boundary.
        return {
            "success": False,
            "response": "Sarthi could not complete that request. Check the backend and model configuration.",
            "error": "desktop_query_failed",
            "action": None,
            "session_id": session_id,
            "trace": trace,
        }
