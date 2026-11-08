"""Sarthi Desktop Pet — lightweight floating pet window.

This module is the renderer only. It does not import backend internals,
make LLM requests, or perform OS automation. It is deliberately isolated
so a future backend event or API response can update its state through
a single controlled interface: set_state(state).

Image assets are resolved relative to this file's project structure,
not the current working directory, so the pet works both in development
and when frozen into an executable.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Image path resolution
# ---------------------------------------------------------------------------

# Image folder is at Desktop/Hitori relative to the project root.
# From pet.py (Desktop/client/sarthi_client/), go up 2 levels to Desktop/,
# then add Hitori/ folder.
# parent = sarthi_client, parent.parent = client, parent.parent.parent = Desktop
_DESKTOP_DIR = Path(__file__).resolve().parent.parent.parent
# PyInstaller extracts bundled data beneath _MEIPASS. In a source checkout,
# assets live beside run.py under Desktop/Hitori.
_HITORI_DIR = Path(getattr(sys, "_MEIPASS", _DESKTOP_DIR)) / "Hitori"

# Map of supported states to image file names.
# All 5 images exist in the Hitori/ folder.
# Only sleeping displays visually by default; others are available via set_state().
_STATE_TO_FILENAME: dict[str, str] = {
    "sleeping": "sleeping-removebg-preview.png",
    "happy": "happy-removebg-preview.png",
    "thinking": "thinking-removebg-preview.png",
    "working": "working-removebg-preview.png",
    "confused": "sad-removebg-preview.png",  # reuse sad as confused placeholder
}

# Default state when the pet launches (Phase 1 MVP).
DEFAULT_STATE = "happy"
# Tk's transparent-color attribute uses a color key on Windows. Keep the
# window and image label on this unusual color so it does not cover the PNG's
# transparent pixels (or turn ordinary white parts of the artwork invisible).
_TRANSPARENT_COLOR = "#000000"  # Tk's default background color for labels and windows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_image_path(filename: str) -> Path:
    """Return the absolute path for a Hitori image file.

    Falls back to returning the path even if the file does not exist —
    the caller decides how to handle a missing asset.
    """
    return _HITORI_DIR / filename


def _load_photoimage(filename: str, master: tk.Misc | None = None) -> ImageTk.PhotoImage | None:
    """Load a PNG from the Hitori folder and return a Tkinter PhotoImage.

    Returns None if the file cannot be opened — the caller must handle
    the None case gracefully (e.g. display a rectangle with state text).
    """
    try:
        path = _resolve_image_path(filename)
        if not path.is_file():
            return None
        img = Image.open(path)
        # Resize reasonably for a pet: keep aspect ratio, cap at 120px height.
        max_h = 120
        w, h = img.size
        if h > max_h:
            ratio = max_h / h
            img = img.resize((int(w * ratio), max_h), Image.LANCZOS)
        return ImageTk.PhotoImage(img, master=master)
    except Exception:  # pylint: disable=broad-except
        return None


# ---------------------------------------------------------------------------
# Pet window
# ---------------------------------------------------------------------------


class DesktopPet(tk.Toplevel):
    """Floating desktop pet window using Tkinter.

    Parameters
    ----------
    parent: tk.Widget
        The parent window (typically the main SarthiApp root).
    image_filename: str | None
        Override the default image filename. If None the default sleeping
        image from Hitori/ is used.
    """

    def __init__(self, parent: tk.Widget, image_filename: str | None = None) -> None:
        super().__init__(parent)

        self._parent = parent
        self._current_state = DEFAULT_STATE
        self._drag_offset_x = 0
        self._drag_offset_y = 0

        # --- Window decorations: borderless, always-on-top, transient ---
        self.overrideredirect(True)  # no title bar, no borders
        self.wm_attributes("-topmost", True)  # stays above normal windows
        self.wm_attributes("-toolwindow", True)  # compact taskbar icon

        # Transparent background where supported. Tk's color-key transparency
        # works on Windows; other Tk builds may not support this attribute.
        self.configure(bg=_TRANSPARENT_COLOR)
        try:
            self.wm_attributes("-transparentcolor", _TRANSPARENT_COLOR)
        except tk.TclError:
            pass

        # Initial geometry: small, upper-right of the parent screen.
        self.geometry("+100+100")

        # --- Layout: a single label holding the image ---
        self._label = tk.Label(
            self,
            borderwidth=0,
            highlightthickness=0,
            bg=_TRANSPARENT_COLOR,
        )
        self._label.pack(fill=tk.BOTH, expand=True)

        # Load the image.
        if image_filename is not None:
            photo = _load_photoimage(image_filename, master=self)
        else:
            photo = _load_photoimage(_STATE_TO_FILENAME.get(DEFAULT_STATE, ""), master=self)

        if photo is not None:
            self._photo = photo  # keep reference to prevent GC
            self._label.config(image=photo)
        else:
            # Fallback: show state text in a box so the pet is never invisible.
            self._label.config(text=DEFAULT_STATE.title(), bg="white", fg="black")

        # --- Drag handling ---
        self._label.bind("<Button-1>", self._start_drag)
        self._label.bind("<B1-Motion>", self._do_drag)
        self.bind("<Button-1>", self._start_drag)
        self.bind("<B1-Motion>", self._do_drag)

        # --- Close handler: hide instead of destroy so the backend stays alive ---
        self.protocol("WM_DELETE_WINDOW", self.hide)
        # Click the <X> in titlebar-free mode: right-click to close.
        self._close_button = tk.Button(
            self, text="×", command=self.close, font=(tkfont.NORMAL, 10, "bold")
        )
        self._close_button.place(relx=1.0, rely=0.0, anchor="ne", width=16, height=16)

        # Ensure the window stays above the parent even when the parent is focused.
        self.lift()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Change the pet's visual state.

        This is the single controlled interface for a future backend event
        or API response to update the pet's appearance. Only the image
        associated with *state* is displayed; missing assets fall back
        gracefully (text label or default sleeping image).

        Parameters
        ----------
        state: str
            One of: "sleeping", "happy", "thinking", "working", "confused".
        """
        normalized = state.lower().strip()
        filename = _STATE_TO_FILENAME.get(normalized)
        if filename is None:
            # Unknown state — ignore; keep current display.
            return

        self._current_state = normalized
        photo = _load_photoimage(filename, master=self)

        if photo is not None:
            self._photo = photo  # keep reference
            self._label.config(image=photo)
            # Adjust geometry slightly if the new image has different size.
            try:
                w, h = photo.width(), photo.height()
                self.geometry(f"{w}x{h}+{self.winfo_x()}+{self.winfo_y()}")
            except Exception:
                pass
        else:
            # Missing asset: show state name as text fallback.
            self._label.config(text=normalized.title(), bg="white", fg="black")

    # ------------------------------------------------------------------
    # Show / hide
    # ------------------------------------------------------------------

    def hide(self) -> None:
        """Hide the pet window without destroying it.

        The backend process continues running; only the visual window
        is withdrawn. Call ``show()`` or raise the window to restore it.
        """
        self.withdraw()

    def show(self) -> None:
        """Restore / show the pet window."""
        self.deiconify()
        self.lift()

    def close(self) -> None:
        """Close the pet window and destroy it.

        Guarantees that the backend remains independent. This is the
        explicit close action (via the × button or right-click menu).
        """
        self.destroy()

    # ------------------------------------------------------------------
    # Drag logic
    # ------------------------------------------------------------------

    def _start_drag(self, event: tk.Event) -> None:
        """Record the mouse offset for dragging."""
        self._drag_offset_x = event.x
        self._drag_offset_y = event.y

    def _do_drag(self, event: tk.Event) -> None:
        """Move the pet window with the mouse."""
        x = self.winfo_pointerx() - self._drag_offset_x
        y = self.winfo_pointery() - self._drag_offset_y
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# Convenience: auto-launch when the parent SarthiApp starts
# ---------------------------------------------------------------------------


def attach_pet_to(parent: tk.Tk) -> DesktopPet:
    """Create and show a DesktopPet attached to *parent*.

    This is intended to be called from the parent's ``__init__`` or
    ``run`` so the pet starts automatically when the Desktop application
    launches.

    Returns
    -------
    DesktopPet
        The instance so the caller can call ``set_state()``, ``hide()``,
        or ``close()`` later.
    """
    pet = DesktopPet(parent)
    pet.show()
    return pet
