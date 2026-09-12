"""Architecture boundary tests for the client/backend split.

The most important architectural rule of the new layout:

    Desktop client  --HTTP only-->  Backend

These tests lock it from both sides:

    - Desktop client source never imports backend intelligence
      (brain, knowledge, skills, hermes, speech, hands, connectors,
      database, events, api, config) and never touches the network
      outside backend.py
    - Backend source never imports the Desktop client or GUI code

Enforced by parsing every Python file under Desktop/client/ and
Backend/ with ast — import tricks (``importlib``, ``__import__``)
would be caught only by grep, but the tests below combine AST walks
with source greps to catch the realistic violations.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_CLIENT_DIR = REPO_ROOT / "Desktop" / "client"
BACKEND_DIR = REPO_ROOT / "Backend"

# Backend intelligence the client must never import.
BACKEND_INTERNALS = {
    "brain",
    "knowledge",
    "skills",
    "hermes",
    "speech",
    "hands",
    "connectors",
    "database",
    "events",
    "utils",
    "api",
    "config",
    "main",
}

# Modules the client's GUI/controller may use for its own presentation.
ALLOWED_STDLIB_AND_THIRD_PARTY = {"tkinter", "httpx", "sarthi_client"}


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _module_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        return None  # handled separately
    return None


def _imported_names(tree: ast.AST) -> list[str]:
    """Collect every imported top-level module name (import x / from x import y)."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # absolute imports only
                names.append(node.module.split(".")[0])
            elif node.level > 0:
                # Relative import within the client package — fine, but
                # record it so the caller knows the file imports *something*.
                names.append(".relative")
    return names


def _dynamic_import_strings(source: str) -> list[str]:
    """Catch importlib/__import__ usages with a literal module name."""
    found: list[str] = []
    for marker in ("import_module(", "__import__("):
        idx = 0
        while True:
            idx = source.find(marker, idx)
            if idx == -1:
                break
            snippet = source[idx : idx + 120]
            found.append(snippet)
            idx += len(marker)
    return found


class TestDesktopDoesNotImportBackend:
    def test_client_files_exist(self):
        assert DESKTOP_CLIENT_DIR.is_dir()
        assert (DESKTOP_CLIENT_DIR / "sarthi_client" / "gui.py").is_file()

    def test_no_backend_intelligence_imports(self):
        """Every client file: no absolute import of a backend package."""
        violations: list[str] = []
        for path in _python_files(DESKTOP_CLIENT_DIR):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name in _imported_names(tree):
                if name in BACKEND_INTERNALS:
                    violations.append(f"{path.name}: imports {name!r}")
        assert violations == []

    def test_no_dynamic_import_of_backend(self):
        for path in _python_files(DESKTOP_CLIENT_DIR):
            source = path.read_text(encoding="utf-8")
            for snippet in _dynamic_import_strings(source):
                for internal in BACKEND_INTERNALS:
                    assert f"'{internal}'" not in snippet and f'"{internal}"' not in snippet, (
                        f"{path.name}: dynamic import of backend module {internal!r}"
                    )

    def test_http_talks_only_in_backend_module(self):
        """Only sarthi_client/backend.py may import httpx (the network
        boundary); other modules may mention it in comments/docstrings."""
        violations: list[str] = []
        for path in _python_files(DESKTOP_CLIENT_DIR):
            if path.name == "backend.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name in _imported_names(tree):
                if name == "httpx":
                    violations.append(path.name)
        assert violations == [], f"httpx imported outside backend.py: {violations}"

    def test_client_does_not_reference_backend_paths(self):
        """No client file reaches into Backend/ via paths or subprocess.
        Mentions in prose (docstrings) are fine — paths/subprocess calls
        are the violation."""
        for path in _python_files(DESKTOP_CLIENT_DIR):
            source = path.read_text(encoding="utf-8")
            assert "import subprocess" not in source, path.name
            assert 'Path("Backend' not in source, path.name
            assert "Path('Backend" not in source, path.name
            assert '"/Backend/' not in source and "'/Backend/" not in source, path.name

    def test_run_py_includes_only_the_client_on_sys_path(self):
        """The dev launcher must not put Backend/ on sys.path."""
        source = (DESKTOP_CLIENT_DIR.parent / "run.py").read_text(encoding="utf-8")
        assert "Backend" not in source


class TestBackendDoesNotImportDesktop:
    def test_no_desktop_imports_in_backend(self):
        """Backend source never imports the Desktop client or GUI code."""
        violations: list[str] = []
        for path in _python_files(BACKEND_DIR):
            source = path.read_text(encoding="utf-8", errors="replace")
            if "sarthi_client" in source or "Desktop" in source:
                # Whitelist: comments mentioning the architecture are fine;
                # imports are not.
                tree = ast.parse(source)
                for name in _imported_names(tree):
                    if name in {"sarthi_client", "desktop", "Desktop"}:
                        violations.append(f"{path.name}: imports {name!r}")
        assert violations == []

    def test_backend_never_launches_the_gui(self):
        for path in _python_files(BACKEND_DIR):
            source = path.read_text(encoding="utf-8", errors="replace")
            assert "sarthi_client.gui" not in source, path.name
            assert "tkinter" not in source, path.name


class TestLayout:
    def test_root_layout_directories_exist(self):
        for directory in ("Backend", "Desktop", "flutter", "apk", "tests", "docs"):
            assert (REPO_ROOT / directory).is_dir(), directory

    def test_backend_entry_points_in_place(self):
        for name in ("api.py", "main.py", "main-test.py", "sarthi.bat", "config.py"):
            assert (BACKEND_DIR / name).is_file(), name

    def test_desktop_spec_in_place(self):
        assert (REPO_ROOT / "Desktop" / "sarthi_client.spec").is_file()

    def test_pytest_pythonpath_points_at_backend(self):
        """The root pytest config must keep Backend importable (tests/ at root)."""
        try:
            sys.path.remove(str(BACKEND_DIR))
        except ValueError:
            pass
        # pyproject's pythonpath is applied by pytest itself; here we assert
        # the config file declares it (guards against config drift).
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert 'pythonpath = ["Backend", "Desktop/client"]' in pyproject
