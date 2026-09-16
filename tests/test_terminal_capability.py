"""Tests for the TERMINAL capability (cd / echo / create) and the
terminal skill + Hermes tool.

Task 2 acceptance criteria (docs/agent/TASK.md):

    - cd/echo/create are structured, allow-listed hand actions
    - every path op is scoped to allowed_roots; traversal impossible
    - relative paths resolve against the tracked cwd (not the process cwd)
    - the cwd carries between successive actions (end-to-end sequence)
    - create ... with content ... creates AND writes
    - the skill honours test mode (dry-run)
    - the Hermes tool passes the validator gate and delegates to the skill
    - no shell/subprocess anywhere in the new code

No test touches the real filesystem outside tmp_path and no subprocess
is ever started.
"""

import pytest
from hands.desktop import DesktopHand
from hands.desktop.capabilities import ACTIONS, CAPABILITIES, PLANNED_CAPABILITIES, action_spec
from hands.desktop.filesystem import FilesystemBackend, FilesystemScopeError

# ---------------------------------------------------------------------------
# Capability registration
# ---------------------------------------------------------------------------


class TestTerminalCapabilityRegistration:
    def test_terminal_capability_registered(self):
        assert "TERMINAL" in CAPABILITIES
        cap = CAPABILITIES["TERMINAL"]
        assert set(cap.actions) == {"cd", "echo", "create"}

    def test_shell_stays_planned(self):
        """The SHELL capability must NOT be promoted by this work."""
        assert "SHELL" in PLANNED_CAPABILITIES
        assert "SHELL" not in CAPABILITIES

    def test_registry_locks_hold_for_new_actions(self):
        """Every new action has an implementation and a spec — and vice versa."""
        hand = DesktopHand()
        for action in ("cd", "echo", "create"):
            assert action in ACTIONS
            assert action in hand._actions
            assert action_spec(action) != {}

    def test_capability_report_lists_terminal(self):
        report = DesktopHand().capabilities()
        ids = {c["id"] for c in report["implemented"]}
        assert "TERMINAL" in ids


# ---------------------------------------------------------------------------
# Filesystem backend: cwd tracking + scoped ops
# ---------------------------------------------------------------------------


class TestFilesystemCwd:
    @pytest.fixture()
    def fs(self, tmp_path):
        root = tmp_path / "home"
        (root / "documents").mkdir(parents=True)
        return FilesystemBackend(allowed_roots=[str(root)]), root

    def test_cwd_starts_at_first_allowed_root(self, fs):
        backend, root = fs
        assert backend.get_cwd() == root

    def test_cd_into_subdirectory(self, fs):
        backend, root = fs
        resolved = backend.change_directory("documents")
        assert resolved == root / "documents"
        assert backend.get_cwd() == root / "documents"

    def test_cd_outside_scope_refused_and_cwd_unchanged(self, fs, tmp_path):
        backend, root = fs
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        with pytest.raises(FilesystemScopeError):
            backend.change_directory(str(outside))
        assert backend.get_cwd() == root

    def test_cd_traversal_refused(self, fs):
        backend, root = fs
        with pytest.raises(FilesystemScopeError):
            backend.change_directory("../../..")
        assert backend.get_cwd() == root

    def test_cd_to_file_refused(self, fs):
        backend, root = fs
        (root / "notes.txt").write_text("x", encoding="utf-8")
        with pytest.raises(NotADirectoryError):
            backend.change_directory("notes.txt")

    def test_relative_paths_resolve_against_cwd_not_process_cwd(self, fs, monkeypatch):
        backend, root = fs
        monkeypatch.chdir(root.parent)  # process cwd is OUTSIDE the allowed root
        backend.change_directory("documents")
        target = backend.resolve_scoped("notes.txt")
        assert target == root / "documents" / "notes.txt"

    def test_create_file_and_directory(self, fs):
        backend, root = fs
        created_file = backend.create("newfile.txt", kind="file")
        assert created_file.read_text(encoding="utf-8") == ""
        created_dir = backend.create("newdir", kind="directory")
        assert created_dir.is_dir()

    def test_create_existing_file_fails(self, fs):
        backend, root = fs
        backend.create("exists.txt", kind="file")
        with pytest.raises(FileExistsError):
            backend.create("exists.txt", kind="file")

    def test_echo_to_file_writes_text_plus_newline(self, fs):
        backend, root = fs
        written, resolved = backend.echo_to_file("hello world", "out.txt")
        assert written == len(b"hello world\n")
        assert resolved.read_text(encoding="utf-8") == "hello world\n"

    def test_create_outside_scope_refused(self, fs, tmp_path):
        backend, root = fs
        with pytest.raises(FilesystemScopeError):
            backend.create(str(tmp_path / "evil.txt"), kind="file")


# ---------------------------------------------------------------------------
# Hand-level execution (structured results, validation gate)
# ---------------------------------------------------------------------------


class TestHandTerminalActions:
    @pytest.fixture()
    def hand(self, tmp_path):
        root = tmp_path / "home"
        (root / "docs").mkdir(parents=True)
        return DesktopHand(allowed_roots=[str(root)]), root

    def test_cd_returns_structured_result(self, hand):
        h, root = hand
        result = h.execute("cd", path="docs")
        assert result["success"] is True
        assert result["data"]["cwd"] == str(root / "docs")

    def test_cd_outside_scope_structured_failure(self, hand, tmp_path):
        h, _root = hand
        result = h.execute("cd", path=str(tmp_path))
        assert result["success"] is False
        assert result["error"] == "outside_scope"

    def test_cd_missing_argument_rejected(self, hand):
        h, _root = hand
        result = h.execute("cd")
        assert result["success"] is False
        assert result["error"] == "invalid_arguments"

    def test_echo_prints_text(self, hand):
        h, _root = hand
        result = h.execute("echo", text="hello")
        assert result["success"] is True
        assert result["data"]["text"] == "hello"

    def test_echo_to_file_writes_inside_scope(self, hand):
        h, root = hand
        result = h.execute("echo", text="hello", path="out.txt")
        assert result["success"] is True
        assert (root / "out.txt").read_text(encoding="utf-8") == "hello\n"

    def test_create_file_then_write_through_existing_action(self, hand):
        h, root = hand
        created = h.execute("create", path="notes.txt", type="file")
        assert created["success"] is True
        written = h.execute("write_file", path="notes.txt", content="hi")
        assert written["success"] is True
        assert (root / "notes.txt").read_text(encoding="utf-8") == "hi"

    def test_create_directory(self, hand):
        h, root = hand
        result = h.execute("create", path="projects", type="directory")
        assert result["success"] is True
        assert (root / "projects").is_dir()

    def test_create_bad_type_rejected_by_choices_spec(self, hand):
        h, _root = hand
        result = h.execute("create", path="x", type="symlink")
        assert result["success"] is False
        assert result["error"] == "invalid_arguments"

    def test_create_existing_structured_failure(self, hand):
        h, root = hand
        h.execute("create", path="dup.txt", type="file")
        result = h.execute("create", path="dup.txt", type="file")
        assert result["success"] is False
        assert result["error"] == "execution_failed"

    def test_end_to_end_sequence_cwd_carries_between_steps(self, hand):
        """The Task-2 acceptance sequence: cd → create → write → echo."""
        h, root = hand
        assert h.execute("cd", path="docs")["success"] is True
        assert h.execute("create", path="notes.txt", type="file")["success"] is True
        assert h.execute("write_file", path="notes.txt", content="hello world")["success"] is True
        echoed = h.execute("echo", text="done", path="status.txt")
        assert echoed["success"] is True
        # Everything landed in the cd'd directory, not the first root.
        assert (root / "docs" / "notes.txt").read_text(encoding="utf-8") == "hello world"
        assert (root / "docs" / "status.txt").read_text(encoding="utf-8") == "done\n"
        assert not (root / "notes.txt").exists()

    def test_no_subprocess_in_terminal_path(self):
        """Security invariant: the terminal implementation never shells out.

        Scans compiled code objects only (names + constants that are
        actual code references), not docstrings/comments.
        """
        import types

        import hands.desktop.filesystem as fs_mod
        import hands.desktop.hand as hand_mod
        import skills.terminal.main as skill_mod

        def _walk(code: types.CodeType) -> set[str]:
            found: set[str] = set()
            for const in code.co_consts:
                if isinstance(const, types.CodeType):
                    found |= _walk(const)
                elif isinstance(const, str) and const in (
                    "subprocess",
                    "os.system",
                    "popen",
                    "Popen",
                    "eval",
                    "exec",
                ):
                    found.add(const)
            found.update(code.co_names)
            return found

        for mod in (fs_mod, hand_mod, skill_mod):
            names = _walk(mod.__dict__["__spec__"].loader and mod.__loader__.get_code(mod.__name__))
            banned = names & {"subprocess", "os.system", "popen", "Popen"}
            assert not banned, f"{mod.__name__} references shell execution: {banned}"


# ---------------------------------------------------------------------------
# Terminal skill
# ---------------------------------------------------------------------------


class TestTerminalSkill:
    @pytest.fixture()
    def skill(self, tmp_path, monkeypatch):
        from skills.terminal import main as terminal_main
        from skills.terminal.main import TerminalSkill

        root = tmp_path / "home"
        (root / "docs").mkdir(parents=True)
        hand = DesktopHand(allowed_roots=[str(root)])
        monkeypatch.setattr(terminal_main, "_get_hand", lambda: hand)
        return TerminalSkill(), root

    def _intent(self, action, target):
        from brain.intent import Intent

        return Intent(action=action, target=target, confidence=1.0, raw_text=f"{action} {target}")

    def test_manifest_discovered(self):
        """The registry finds the new terminal skill (11 total).

        brain.engine is imported first deliberately — importing
        skills.registry cold triggers a pre-existing import-order cycle
        (skills.base → brain.intent → brain.executor → skills.base).
        """
        import brain.engine  # noqa: F401  (break the cycle first)
        from skills.registry import SkillRegistry

        skills = {s.skill_id for s in SkillRegistry().discover()}
        assert "terminal" in skills

    def test_cd(self, skill):
        s, root = skill
        result = s.execute(self._intent("cd", "docs"))
        assert result["success"] is True
        assert result["result"]["cwd"] == str(root / "docs")

    def test_echo_plain(self, skill):
        s, _root = skill
        result = s.execute(self._intent("echo", "hello there"))
        assert result["success"] is True
        assert result["result"]["text"] == "hello there"

    def test_echo_to_file(self, skill):
        s, root = skill
        result = s.execute(self._intent("echo", "hello to out.txt"))
        assert result["success"] is True
        assert (root / "out.txt").read_text(encoding="utf-8") == "hello\n"

    def test_create_file(self, skill):
        s, root = skill
        result = s.execute(self._intent("create", "file notes.txt"))
        assert result["success"] is True
        assert (root / "notes.txt").exists()

    def test_create_directory(self, skill):
        s, root = skill
        result = s.execute(self._intent("create", "directory projects"))
        assert result["success"] is True
        assert (root / "projects").is_dir()

    def test_create_with_content(self, skill):
        s, root = skill
        result = s.execute(self._intent("create", "file notes.txt with content hello world"))
        assert result["success"] is True
        assert (root / "notes.txt").read_text(encoding="utf-8") == "hello world"

    def test_write_to_file(self, skill):
        s, root = skill
        result = s.execute(self._intent("write", "hello world to notes.txt"))
        assert result["success"] is True
        # write_file semantics: verbatim content, no trailing newline.
        assert (root / "notes.txt").read_text(encoding="utf-8") == "hello world"

    def test_write_without_file_target(self, skill):
        s, _root = skill
        result = s.execute(self._intent("write", "just some text"))
        assert result["success"] is False
        assert result.get("handled") is True

    def test_cd_outside_scope_structured_failure(self, skill, tmp_path):
        s, _root = skill
        result = s.execute(self._intent("cd", str(tmp_path)))
        assert result["success"] is False
        assert result.get("handled") is True
        assert result.get("error")

    def test_unknown_action(self, skill):
        s, _root = skill
        result = s.execute(self._intent("rm", "everything"))
        assert result["success"] is False
        assert result["status"] == "unknown_action"

    def test_test_mode_dry_run(self, skill, monkeypatch):
        import skills.terminal.main as terminal_main

        s, root = skill
        monkeypatch.setattr(terminal_main, "get_test_mode", lambda: True)
        result = s.execute(self._intent("create", "file dryrun.txt"))
        assert result["success"] is True
        assert result["status"] == "test_mode"
        assert not (root / "dryrun.txt").exists()


# ---------------------------------------------------------------------------
# Hermes tool bridge
# ---------------------------------------------------------------------------


class TestTerminalTool:
    @pytest.fixture()
    def tool(self, tmp_path, monkeypatch):
        from hermes.tools.terminal import TerminalTool
        from skills.terminal import main as terminal_main

        root = tmp_path / "home"
        (root / "docs").mkdir(parents=True)
        hand = DesktopHand(allowed_roots=[str(root)])
        monkeypatch.setattr(terminal_main, "_get_hand", lambda: hand)
        return TerminalTool(), root

    def test_registered_in_default_tools(self):
        from hermes.tool_registry import ToolRegistry
        from hermes.tools import TerminalTool, register_default_tools

        registry = ToolRegistry()
        register_default_tools(registry)
        assert "terminal" in registry.tool_names()
        assert isinstance(registry.get("terminal"), TerminalTool)

    def test_tool_count_is_eleven(self):
        from hermes.tool_registry import ToolRegistry
        from hermes.tools import register_default_tools

        registry = ToolRegistry()
        register_default_tools(registry)
        assert len(registry.tool_names()) == 11

    def test_validator_gate_accepts_valid_arguments(self, tool):
        from hermes.tool_registry import validate_arguments

        t, _root = tool
        assert validate_arguments(t.parameters, {"action": "cd", "target": "docs"}) is None
        assert validate_arguments(t.parameters, {"action": "cd"}) is not None
        assert (
            validate_arguments(t.parameters, {"action": "rm", "target": "x"}) is None
        )  # shape-only

    def test_execute_cd(self, tool):
        t, root = tool
        result = t.execute({"action": "cd", "target": "docs"})
        assert result.success is True
        assert result.data["cwd"] == str(root / "docs")

    def test_execute_write(self, tool):
        t, root = tool
        result = t.execute({"action": "write", "target": "hi there to f.txt"})
        assert result.success is True
        # "write" maps onto write_file: content written verbatim, no newline
        # appended (use "echo ... to <file>" for the newline behaviour).
        assert (root / "f.txt").read_text(encoding="utf-8") == "hi there"

    def test_execute_rejects_unknown_action(self, tool):
        t, _root = tool
        result = t.execute({"action": "rm", "target": "x"})
        assert result.success is False
        assert result.invalid is True

    def test_execute_rejects_missing_target(self, tool):
        t, _root = tool
        result = t.execute({"action": "echo", "target": ""})
        assert result.success is False
        assert result.invalid is True

    def test_registry_dispatch_end_to_end(self, tool, monkeypatch, tmp_path):
        """Through ToolRegistry.execute — the way Hermes actually calls it."""
        from hermes.tool_registry import ToolRegistry
        from hermes.tools import register_default_tools

        t, root = tool
        registry = ToolRegistry()
        register_default_tools(registry)
        result = registry.execute("terminal", {"action": "create", "target": "file a.txt"})
        assert result.success is True
        assert (root / "a.txt").exists()
