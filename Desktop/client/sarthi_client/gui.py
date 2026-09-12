"""Sarthi Desktop client — tkinter GUI.

Deliberately minimal: title, a query textbox, a Send button, and a
response area. It proves the Desktop -> Network -> Backend -> Response ->
Desktop loop. The full Stitch dashboard intentionally does NOT live here.

Presentation only: every action goes through SarthiController, which
talks to the Backend over HTTP. No backend intelligence is imported.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from .controller import SarthiController

# Window defaults
WINDOW_TITLE = "Sarthi"
WINDOW_SIZE = "460x300"
WINDOW_MIN_SIZE = (380, 240)


class SarthiApp:
    """The SARTHI window: Query textbox → Send → Response area."""

    def __init__(self, controller: SarthiController | None = None):
        self.controller = controller or SarthiController()
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(*WINDOW_MIN_SIZE)
        self._build_widgets()

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        heading_font = tkfont.Font(size=15, weight="bold")

        # Title
        self.title_label = tk.Label(self.root, text="SARTHI", font=heading_font, pady=6)
        self.title_label.grid(row=0, column=0, sticky="ew")

        # Query row: label + textbox + Send button
        query_row = tk.Frame(self.root)
        query_row.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
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
        self.response_label.grid(row=2, column=0, sticky="ew", padx=10)

        # Response area
        self.response_box = tk.Text(self.root, height=6, state=tk.DISABLED, wrap=tk.WORD)
        self.response_box.grid(row=3, column=0, sticky="nsew", padx=10, pady=(2, 4))

        # Status bar
        self.status_var = tk.StringVar(value=f"Backend: {self.controller.backend_url}")
        status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            bd=1,
            relief=tk.SUNKEN,
        )
        status_bar.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def on_send(self) -> None:
        """Send the textbox content through the controller and render it."""
        self.send_button.config(state=tk.DISABLED)
        try:
            result = self.controller.send(self.query_entry.get())
        finally:
            self.send_button.config(state=tk.NORMAL)

        self._show_response(result.display_text)
        self.status_var.set(result.status_text)

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
