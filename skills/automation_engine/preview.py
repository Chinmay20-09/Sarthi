"""
Preview Generator for the Automation Engine.

Generates human-readable previews of proposed changes
before applying them.

Status: Stub — not yet fully implemented.
"""


class PreviewGenerator:
    """Placeholder for preview generation logic."""

    def show(self, responses) -> None:
        """Display a preview of assistant responses."""
        print("\nPreview: Automation changes pending")
        for response in responses:
            print(f"  - {response.assistant}: {response.summary}")
