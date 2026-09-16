"""Brain/Hand boundary tests.

The architectural rule locked here:

    Backend = Brain — interprets, routes, plans, validates, decides.
    Desktop = Hand  — executes authorized actions and observes; never reasons.

The Brain programs against the ``Hand`` interface (``hands.base.Hand``);
``DesktopHand`` is the local (same-machine) implementation. A future
``RemoteDesktopHand`` would implement the same contract over a network
protocol without the Brain changing.

What these tests prove (brief §13):

1. Backend can issue an action through the Hand abstraction.
2. LocalHand executes the action using the existing executor/hand.
3. Backend remains the caller/authority.
4. Desktop/Hand contains no Hermes/model reasoning (import-level lock).
5. Simple deterministic commands still work (no Hermes wake).
6. Complex commands still route to Hermes.
7. Hermes reaches the OS only through the existing tool bridge.
8. Execution results return to the Backend as structured dicts.
9. No duplicate Hermes loop / duplicate hand abstraction exists.
10. Existing tests continue passing (run the full suite).

Prefer contract/architecture tests over big mocked integrations, mirroring
the style of tests/test_architecture_boundaries.py and
tests/test_consolidation_routing.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "Backend"
HANDS_DIR = BACKEND_DIR / "hands"

# Intelligence the Hand must never import: the hand performs, the Brain
# decides. Importing any of these would make the hand a second brain.
BRAIN_MODULES = {"brain", "hermes", "knowledge", "api", "skills"}


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _imported_names(tree: ast.AST) -> list[str]:
    """Top-level module names imported by a file (import x / from x import y)."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.append(node.module.split(".")[0])
    return names


# ---------------------------------------------------------------------------
# 1–3. The Hand contract: the Brain issues actions through the interface
# ---------------------------------------------------------------------------


class TestHandContract:
    def test_desktop_hand_satisfies_the_hand_protocol(self):
        """The local hand implements the Brain/Hand contract (brief §4/§5)."""
        from hands.base import Hand
        from hands.desktop import DesktopHand

        assert isinstance(DesktopHand(), Hand)

    def test_backend_issues_actions_through_the_hand_interface(self):
        """The executor's close flow programs against ``Hand``, not the
        concrete hand — the boundary the Brain is required to use."""
        executor_source = (BACKEND_DIR / "brain" / "executor.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "from hands.base import Hand" in executor_source
        assert "hand: Hand = get_desktop_hand()" in executor_source
        # The seam is hands.local.get_desktop_hand — the local/remote mode
        # resolver behind which the IPC transport hides (Brain↔Desktop Agent).
        assert "from hands.local import get_desktop_hand" in executor_source

    def test_hand_contract_has_no_reasoning_surface(self):
        """The protocol exposes only perform/observe members — no interpret,
        no plan, no route, no LLM call could ever satisfy it."""
        import inspect

        from hands import base

        members = {name for name, _ in inspect.getmembers(base.Hand, predicate=inspect.isfunction)}
        assert {"execute", "capabilities", "find_application_process"} <= members
        forbidden = {
            "interpret",
            "plan",
            "route",
            "decide",
            "classify",
            "reason",
            "chat",
            "run",
            "generate",
        }
        assert members & forbidden == set()

    def test_backend_remains_the_authority(self, monkeypatch):
        """The Brain calls the hand with an explicit, authorized action and
        explicit arguments; the hand never sees the user's sentence."""
        from hands.base import Hand

        seen: list[tuple[str, dict]] = []

        class RecordingHand:
            """Minimal Hand-shaped stand-in (structural conformance)."""

            def execute(self, action, target=None, **kwargs):
                seen.append((action, kwargs))
                return {
                    "success": True,
                    "action": action,
                    "target": target,
                    "message": "closed",
                    "error": None,
                    "data": {},
                }

            def capabilities(self):
                return {"implemented": [], "planned": []}

            def find_application_process(self, exe_name):
                return [{"pid": 4242, "name": "chrome.exe"}]

        assert isinstance(RecordingHand(), Hand)

        from brain.executor import BrainExecutor
        from brain.intent import Intent

        executor = BrainExecutor()
        import knowledge.manager as knowledge_manager_module

        monkeypatch.setattr(
            knowledge_manager_module,
            "get_manager",
            lambda: type(
                "K",
                (),
                {
                    "find_application": staticmethod(
                        lambda t: {"name": "Chrome", "path": "C:/x/chrome.exe"}
                    )
                },
            )(),
        )
        # Patch the package-level binding the executor's handler actually
        # imports (``from hands.desktop import get_desktop_hand``) so the
        # fake hand — never a real process — receives the action.
        import hands.desktop as hands_desktop_package

        monkeypatch.setattr(hands_desktop_package, "get_desktop_hand", lambda: RecordingHand())

        result = executor.execute(Intent(action="close", target="chrome"))

        assert result["success"] is True
        assert result["result"]["closed"] == 1  # observation returned to the Brain
        # The Brain issued one explicit authorized action with an explicit pid.
        assert seen == [("close_application", {"pid": 4242})]


# ---------------------------------------------------------------------------
# 2 & 8. LocalHand executes with existing mechanisms; results come back
# ---------------------------------------------------------------------------


class TestLocalHandExecution:
    def test_hand_executes_validated_action_and_returns_structured_result(self, monkeypatch):
        """A validated action runs the existing process backend and returns a
        DesktopResult-shaped dict — observation flows back to the Brain."""
        import hands.desktop.processes as process_backend
        from hands.desktop import DesktopHand

        killed: list[int] = []

        monkeypatch.setattr(
            process_backend, "terminate_process", lambda pid: killed.append(pid) or True
        )

        hand = DesktopHand()
        result = hand.execute("close_application", target="chrome", pid=3113)

        assert killed == [3113]
        assert result["success"] is True
        assert result["action"] == "close_application"
        assert result["target"] == "chrome"
        assert "message" in result
        assert "error" not in result or result["error"] is None

    def test_hand_rejects_unauthorized_actions_without_executing(self, monkeypatch):
        """Allow-list enforcement: an action outside the capability map is
        refused structurally — the hand cannot be talked into arbitrary OS
        operations (brief §10: authorization stays with the Backend)."""
        import hands.desktop.input as input_backend
        from hands.desktop import DesktopHand

        typed: list[str] = []

        monkeypatch.setattr(input_backend, "type_text", lambda text: typed.append(text))

        hand = DesktopHand()
        result = hand.execute("format_c_drive")

        assert result["success"] is False
        assert result["error"] == "unknown_action"
        assert typed == []  # nothing ran

    def test_hand_reports_failures_instead_of_raising(self, monkeypatch):
        """Expected operational failures return a structured result (never
        raised past the boundary) — the Brain receives an observation."""
        import hands.desktop.processes as process_backend
        from hands.desktop import DesktopHand

        monkeypatch.setattr(
            process_backend,
            "terminate_process",
            lambda pid: (_ for _ in ()).throw(FileNotFoundError("gone")),
        )

        result = DesktopHand().execute("close_application", target="x", pid=99)

        assert result["success"] is False
        assert result["error"] == "not_found"
        assert result["message"]


# ---------------------------------------------------------------------------
# 4. The Hand contains no model/reasoning dependency
# ---------------------------------------------------------------------------


class TestHandHasNoBrain:
    def test_hands_never_import_brain_modules(self):
        """AST lock (brief §6): hands/ must not import brain, hermes,
        knowledge, api or skills — no NL interpretation, no LLM, no
        competing planner can live in the hand."""
        violations: list[str] = []
        for path in _python_files(HANDS_DIR):
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            for name in _imported_names(tree):
                if name in BRAIN_MODULES:
                    violations.append(f"{path.name}: imports {name!r}")
        assert violations == []

    def test_hands_source_has_no_llm_or_network_server_references(self):
        """Source-level check: no LLM client, no HTTP server framework and no
        tool-planner remnants under hands/ — the hand stays a dumb executor."""
        forbidden = [
            "import hermes",
            "from hermes",
            "openai",
            "anthropic",
            "ollama",
            "fastapi",
            "uvicorn",
            "websocket",
            "ToolPlanner",
            "HermesAgent",
            "tool_registry",
        ]
        violations: list[str] = []
        for path in _python_files(HANDS_DIR):
            source = path.read_text(encoding="utf-8", errors="replace").lower()
            for needle in forbidden:
                if needle.lower() in source:
                    violations.append(f"{path.name}: contains {needle!r}")
        assert violations == []


# ---------------------------------------------------------------------------
# 5–7 & 9. Routing stays as consolidated; Hermes reaches the OS only via
# the tool bridge; exactly one loop and one hand abstraction exist
# ---------------------------------------------------------------------------


class TestRoutingAndSingleLoopPreserved:
    def test_simple_command_is_deterministic(self, monkeypatch):
        """\"open chrome\" resolves and executes without any Hermes call
        (brief §8 — the deterministic path must not wake the model)."""
        import knowledge.manager as knowledge_manager_module
        from brain.engine import BrainEngine

        monkeypatch.setattr(
            knowledge_manager_module,
            "get_manager",
            lambda: type(
                "K",
                (),
                {
                    "find_application": staticmethod(
                        lambda t: {"name": "Chrome", "path": "C:/x/chrome.exe"}
                    )
                },
            )(),
        )
        import skills.app_launcher.main as app_launcher_module

        monkeypatch.setattr(
            app_launcher_module.AppLauncherSkill,
            "_launch_path",
            staticmethod(lambda path: None),
        )

        result = BrainEngine().process("open chrome")
        assert result.success is True

    def test_complex_command_routes_to_hermes(self):
        """A compound research-shaped command scores complex (router only,
        no model — mirrors test_consolidation_routing.py)."""
        from hermes.router import route_command

        route = route_command("research the best python ides and compare them in a table")
        assert route.route == "hermes"

    def test_hermes_tools_delegate_never_execute_the_os_directly(self):
        """The Hermes-facing tool bridge delegates to existing skills/executor
        (open_app → AppLauncherSkill; close_app → BrainExecutor) — Hermes has
        no path to the OS except through Sarthi's capability layer."""
        tools_dir = BACKEND_DIR / "hermes" / "tools"
        forbidden = ("subprocess", "os.system", "pyautogui", "psutil", "startfile")
        violations: list[str] = []
        for path in _python_files(tools_dir):
            source = path.read_text(encoding="utf-8", errors="replace")
            for needle in forbidden:
                if f"{needle}(" in source or f"import {needle}" in source:
                    violations.append(f"{path.name}: uses {needle!r}")
        assert violations == []

    def test_no_duplicate_hermes_loop_exists(self):
        """The consolidation's single-loop rule still holds: the ToolPlanner
        class is gone, the agent is the only model/tool loop."""
        planner_source = (BACKEND_DIR / "hermes" / "tool_planner.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "class ToolPlanner" not in planner_source

        agent_source = (BACKEND_DIR / "hermes" / "agent.py").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "class HermesAgent" in agent_source

    def test_no_duplicate_hand_abstraction_was_created(self):
        """Exactly one Hand implementation exists — no desktop_executor.py /
        remote_executor.py / hand_manager.py / device_agent.py doubles."""
        for banned in (
            "desktop_executor.py",
            "remote_executor.py",
            "action_executor.py",
            "hand_manager.py",
            "device_agent.py",
        ):
            assert not (BACKEND_DIR / banned).exists(), banned

        hand_files = [
            p.name
            for p in HANDS_DIR.rglob("*.py")
            if "class DesktopHand" in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert hand_files == ["hand.py"]


# ---------------------------------------------------------------------------
# 5–6 (API-level). Simple commands never reach Hermes; complex ones do —
# locked at the /command gate exactly as the consolidation left it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["open chrome", "open youtube and search lofi", "close notepad"],
)
def test_simple_commands_do_not_look_like_task_instructions(text):
    from hermes.router import looks_like_task_instruction

    assert looks_like_task_instruction(text) is False


def test_task_shaped_instruction_is_flagged():
    from hermes.router import looks_like_task_instruction

    assert (
        looks_like_task_instruction("find all assignment pdfs and rename them by subject") is True
    )
