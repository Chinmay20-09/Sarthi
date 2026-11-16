"""Sarthi Desktop client — tkinter GUI.

Deliberately minimal: title, a query textbox, a Send button, and a
response area. It proves the Desktop -> Network -> Backend -> Response ->
Desktop loop. The full Stitch dashboard intentionally does NOT live here.

Presentation only: every action goes through SarthiController, which
talks to the Backend over HTTP. No backend intelligence is imported.
The desktop pet (optional) is launched from this module so it starts
auto-matically when the window opens.
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from queue import Empty, Queue
from tkinter import font as tkfont
from tkinter import ttk
from urllib.parse import urlsplit

from .controller import SarthiController
from .pet import attach_pet_to  # optional desktop pet

# Window defaults
WINDOW_TITLE = "Sarthi"
WINDOW_SIZE = "520x380"
WINDOW_MIN_SIZE = (420, 320)
PROFILE_OPTIONS = {
    "Low — 3B model": "low",
    "Medium — 8B Q3 model": "medium",
    "High — configured model": "high",
}
PROFILE_LABELS = {profile: label for label, profile in PROFILE_OPTIONS.items()}
PET_STATES = {"sleeping", "happy", "thinking", "working", "confused", "sad"}


class SarthiApp:
    """The SARTHI window: Query textbox → Send → Response area."""

    def __init__(self, controller: SarthiController | None = None):
        self.controller = controller or SarthiController()
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(*WINDOW_MIN_SIZE)
        self._build_widgets()
        self._ui_queue: Queue[tuple[object, tuple]] = Queue()
        self.root.after(50, self._drain_ui_queue)

        # Launch the optional desktop pet (borderless, always-on-top).
        # It does not depend on backend internals — it only uses the existing
        # Hitori image assets and Tkinter.
        self.pet = attach_pet_to(self.root)
        self.load_model_profile()

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(4, weight=1)

        heading_font = tkfont.Font(size=15, weight="bold")

        # Title
        self.title_label = tk.Label(self.root, text="SARTHI", font=heading_font, pady=6)
        self.title_label.grid(row=0, column=0, sticky="ew")

        # Local model profile selector; reads and writes through HTTP only.
        profile_row = tk.Frame(self.root)
        profile_row.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        profile_row.columnconfigure(1, weight=1)
        tk.Label(profile_row, text="Local model profile:").grid(row=0, column=0, padx=(0, 6))
        self.profile_var = tk.StringVar(value=PROFILE_LABELS["low"])
        self.profile_select = ttk.Combobox(
            profile_row,
            textvariable=self.profile_var,
            values=tuple(PROFILE_OPTIONS),
            state="readonly",
        )
        self.profile_select.grid(row=0, column=1, sticky="ew")
        self.profile_save_button = tk.Button(
            profile_row, text="Save", width=8, command=self.on_save_profile
        )
        self.profile_save_button.grid(row=0, column=2, padx=(6, 0))
        self.profile_status_var = tk.StringVar(value="Loading saved model profile…")
        tk.Label(
            profile_row,
            textvariable=self.profile_status_var,
            anchor="w",
            fg="#555555",
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(3, 0))

        # Query row: label + textbox + Send button
        query_row = tk.Frame(self.root)
        query_row.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        query_row.columnconfigure(1, weight=1)

        tk.Label(query_row, text="Query:").grid(row=0, column=0, padx=(0, 6))
        self.query_entry = tk.Entry(query_row)
        self.query_entry.grid(row=0, column=1, sticky="ew")
        self.query_entry.bind("<Return>", lambda _event: self.on_send())
        self.query_entry.focus_set()

        self.send_button = tk.Button(query_row, text="Send", width=10, command=self.on_send)
        self.send_button.grid(row=0, column=2, padx=(6, 0))

        # Response label
        self.response_label = tk.Label(self.root, text="Response:", anchor="w")
        self.response_label.grid(row=3, column=0, sticky="ew", padx=10)

        # Response area
        self.response_box = tk.Text(self.root, height=6, state=tk.DISABLED, wrap=tk.WORD)
        self.response_box.grid(row=4, column=0, sticky="nsew", padx=10, pady=(2, 4))

        # Status bar
        self.status_var = tk.StringVar(value=f"Backend: {self.controller.backend_url}")
        status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            bd=1,
            relief=tk.SUNKEN,
        )
        status_bar.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 8))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def load_model_profile(self) -> None:
        """Load the saved model profile without blocking window startup."""
        get_profile = getattr(self.controller, "get_model_profile", None)
        if not callable(get_profile):
            self.profile_status_var.set("Profile settings unavailable.")
            return
        threading.Thread(target=self._load_profile_worker, args=(get_profile,), daemon=True).start()

    def _load_profile_worker(self, get_profile) -> None:
        try:
            result = get_profile()
        except Exception as exc:
            result = {"success": False, "detail": str(exc)}
        self._ui_queue.put((self._apply_loaded_profile, (result,)))

    def _apply_loaded_profile(self, result: dict) -> None:
        profile = result.get("profile")
        if result.get("success") and profile in PROFILE_LABELS:
            self.profile_var.set(PROFILE_LABELS[profile])
            self.profile_status_var.set(f"Active profile: {PROFILE_LABELS[profile]}")
        else:
            self.profile_status_var.set("Could not load saved profile; Low remains selected.")

    def on_save_profile(self) -> None:
        """Save the selected profile without blocking the Tk event loop."""
        profile = PROFILE_OPTIONS.get(self.profile_var.get())
        if profile is None:
            self.profile_status_var.set("Choose Low, Medium, or High.")
            return
        save_profile = getattr(self.controller, "set_model_profile", None)
        if not callable(save_profile):
            self.profile_status_var.set("Profile settings unavailable.")
            return
        self.profile_save_button.config(state=tk.DISABLED)
        threading.Thread(
            target=self._save_profile_worker, args=(save_profile, profile), daemon=True
        ).start()

    def _save_profile_worker(self, save_profile, profile: str) -> None:
        try:
            result = save_profile(profile)
        except Exception as exc:
            result = {"success": False, "detail": str(exc)}
        self._ui_queue.put((self._finish_profile_save, (result, profile)))

    def _finish_profile_save(self, result: dict, profile: str) -> None:
        self.profile_save_button.config(state=tk.NORMAL)
        if result.get("success"):
            self.profile_status_var.set(
                f"Saved {PROFILE_LABELS[profile]}. Applies to the next query."
            )
        else:
            detail = result.get("detail") or result.get("error") or "backend error"
            self.profile_status_var.set(f"Could not save profile: {detail}")

    def on_send(self) -> None:
        """Run routing/network work off the Tk event loop."""
        query = self.query_entry.get()
        self.send_button.config(state=tk.DISABLED)
        threading.Thread(target=self._send_worker, args=(query,), daemon=True).start()

    def _send_worker(self, query: str) -> None:
        """Do potentially slow inventory/network/model work away from Tk."""
        try:
            result = self.controller.send(query)
        except Exception as exc:
            from .controller import SendResult

            result = SendResult("", f"Sarthi could not complete the request: {exc}")
        self._ui_queue.put((self._finish_send, (result,)))

    def _drain_ui_queue(self) -> None:
        """Apply worker results on Tk's main thread only."""
        try:
            while True:
                callback, args = self._ui_queue.get_nowait()
                try:
                    callback(*args)
                except Exception as exc:
                    self.status_var.set(f"Could not update the window: {exc}")
        except Empty:
            pass
        try:
            self.root.after(50, self._drain_ui_queue)
        except tk.TclError:
            # The user closed the window; queued work can be discarded.
            pass

    def _finish_send(self, result) -> None:
        """Apply the completed request result on Tk's main thread."""
        self.send_button.config(state=tk.NORMAL)

        display_text = result.display_text
        status_text = result.status_text
        for client_action in result.client_actions:
            success, action_message = self._execute_client_action(client_action)
            if not success:
                display_text = action_message
                status_text = "Desktop action failed."
                break
            status_text = action_message

        self._show_response(display_text)
        self.status_var.set(status_text)
        if result.pet_state:
            self.pet.set_state(result.pet_state)

    def _execute_client_action(self, action: dict) -> tuple[bool, str]:
        """Run a small, explicit client-side action returned by the backend."""
        action_type = action.get("type")
        if action_type == "set_pet_state":
            state = action.get("state")
            if not isinstance(state, str) or state not in PET_STATES:
                return False, "The backend requested an unsupported pet state."
            try:
                self.pet.set_state(state)
                self.pet.show()
            except Exception:
                return False, "Could not update the desktop pet."
            return True, f"Desktop pet changed to {state}."

        if action_type == "open_url":
            url = action.get("url")
            if not isinstance(url, str) or len(url) > 2048:
                return False, "The backend returned an invalid URL."
            try:
                parsed = urlsplit(url)
            except ValueError:
                return False, "The backend returned an invalid URL."
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                return False, "Only valid HTTP or HTTPS links can be opened."
            try:
                opened = webbrowser.open(url, new=2)
            except Exception:
                opened = False
            if not opened:
                return False, "Could not open the link in the desktop browser."
            return True, "Opened the link in the desktop browser."

        return False, "The backend returned an unsupported desktop action."

    # ------------------------------------------------------------------
    # Rendering helpers (overridable seams for tests)
    # ------------------------------------------------------------------

    def _show_response(self, text: str) -> None:
        """Replace the response area's content (read-only otherwise)."""
        self.response_box.config(state=tk.NORMAL)
        self.response_box.delete("1.0", tk.END)
        self.response_box.insert(tk.END, text)
        self.response_box.config(state=tk.DISABLED)

    def run(self) -> None:
        """Start the tkinter main loop (blocks until the window closes)."""
        self.root.mainloop()


def main() -> None:
    """Entry point: build the controller and launch the window."""
    SarthiApp().run()


if __name__ == "__main__":
    main()
