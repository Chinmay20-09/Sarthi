"""Filesystem backends for the Desktop hand — explicit paths, scoped roots.

Rules:
    - Every path is resolved and checked against an allow-list of root
      directories (default: the user's profile). Absolute paths outside
      the roots are refused — no traversal via ``..`` or UNC tricks.
    - Only regular files are read/written/deleted. Directory creation is
      limited to one level inside an allowed root.
    - Reads return text (UTF-8, errors replaced); a size cap keeps a
      stray read from loading gigabytes into memory.
    - The backend tracks a working directory (``cwd``) for the
      TERMINAL capability: it starts at the first allowed root and is
      changed only by ``change_directory`` (which re-checks the scope).
      Relative paths in every operation resolve against this cwd, never
      against the process working directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["FilesystemBackend", "FilesystemScopeError"]

# Refuse reads beyond this size (1 MB) — Desktop is not a bulk ETL tool.
MAX_READ_BYTES = 1_000_000


class FilesystemScopeError(PermissionError):
    """Raised when a path falls outside the configured allowed roots."""


class FilesystemBackend:
    """Scoped file operations with an explicit allow-list of roots."""

    def __init__(self, allowed_roots: list[str] | None = None):
        """Configure the scope. Defaults to the user's home directory."""
        if allowed_roots:
            roots = allowed_roots
        else:
            home = Path.home()
            roots = [str(home)]
        self.allowed_roots = [Path(r).resolve() for r in roots]
        # Process-lifetime working directory for terminal-style commands.
        # Starts at the first allowed root; changed only via change_directory.
        self._cwd = self.allowed_roots[0]

    # ------------------------------------------------------------------
    # Scope validation
    # ------------------------------------------------------------------

    def resolve_scoped(self, path: str | Path) -> Path:
        """Resolve a path and verify it lies under one of the allowed roots.

        Relative paths resolve against the tracked cwd (starting at the
        first allowed root), not the process working directory.

        Raises FilesystemScopeError otherwise. Resolution absorbs ``..``
        and symlink-free relative segments, so traversal attempts fail
        the containment check.
        """
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self._cwd / candidate
        resolved = candidate.resolve()
        for root in self.allowed_roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise FilesystemScopeError(f"Path is outside the allowed filesystem roots: {resolved}")

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def read_file(self, path: str | Path, max_bytes: int = MAX_READ_BYTES) -> str:
        """Read a text file (UTF-8) inside the scope."""
        target = self.resolve_scoped(path)
        if not target.is_file():
            raise FileNotFoundError(f"Not a file: {target}")
        size = target.stat().st_size
        if size > max_bytes:
            raise ValueError(f"File too large to read ({size} bytes > {max_bytes})")
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str | Path, content: str, max_bytes: int = MAX_READ_BYTES) -> int:
        """Write text to a file inside the scope. Returns bytes written."""
        target = self.resolve_scoped(path)
        payload = content.encode("utf-8")
        if len(payload) > max_bytes:
            raise ValueError(f"Content too large to write ({len(payload)} bytes > {max_bytes})")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        logger.debug(f"[Desktop] wrote {len(payload)} bytes to {target}")
        return len(payload)

    def delete_file(self, path: str | Path) -> bool:
        """Delete a file inside the scope. True when it existed."""
        target = self.resolve_scoped(path)
        if not target.is_file():
            return False
        target.unlink()
        logger.debug(f"[Desktop] deleted {target}")
        return True

    def list_directory(self, path: str | Path) -> list[dict]:
        """List one directory level inside the scope (no recursion)."""
        target = self.resolve_scoped(path)
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")
        entries = []
        for child in sorted(target.iterdir()):
            kind = "dir" if child.is_dir() else "file"
            size = child.stat().st_size if child.is_file() else 0
            entries.append({"name": child.name, "type": kind, "size": size})
        return entries

    # ------------------------------------------------------------------
    # Terminal-style operations (TERMINAL capability)
    # ------------------------------------------------------------------

    def get_cwd(self) -> Path:
        """The tracked working directory (always inside an allowed root)."""
        return self._cwd

    def change_directory(self, path: str | Path) -> Path:
        """Change the tracked working directory (``cd``).

        The target must resolve inside an allowed root — otherwise
        FilesystemScopeError is raised and the cwd is left unchanged.
        Returns the resolved absolute directory.
        """
        target = self.resolve_scoped(path)
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")
        self._cwd = target
        logger.debug(f"[Desktop] cwd -> {target}")
        return target

    def create(self, path: str | Path, kind: str = "file") -> Path:
        """Create an empty file or a directory inside the scope.

        Fails with FileExistsError when the target already exists.
        Parent directories are created as needed (same policy as
        ``write_file``). Returns the resolved path.
        """
        target = self.resolve_scoped(path)
        if kind == "directory":
            target.mkdir(parents=True, exist_ok=False)
        elif kind == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(exist_ok=False)
        else:
            raise ValueError(f"Unknown create kind: {kind!r} (expected 'file' or 'directory')")
        logger.debug(f"[Desktop] created {kind}: {target}")
        return target

    def echo_to_file(self, text: str, path: str | Path) -> tuple[int, Path]:
        """Write ``text`` (+ newline) to a file inside the scope (``echo ... to``).

        Same size cap as ``write_file``. Returns (bytes written, resolved
        path). Existing files are overwritten, matching ``write_file``.
        """
        target = self.resolve_scoped(path)
        payload = (text + "\n").encode("utf-8")
        if len(payload) > MAX_READ_BYTES:
            raise ValueError(f"Content too large to write ({len(payload)} bytes)")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        logger.debug(f"[Desktop] echo wrote {len(payload)} bytes to {target}")
        return len(payload), target
