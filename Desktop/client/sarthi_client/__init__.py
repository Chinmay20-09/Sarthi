"""sarthi_client — the Sarthi Desktop client.

A thin Windows client for the Sarthi Backend. It contains NO assistant
intelligence: it sends the user's query to the Backend API over HTTP and
displays the response. All processing (model, interpreter, brain,
knowledge, skills, executor) lives in Backend/.

The desktop pet (optional) is available via :py:mod:`pet` and starts
auto-matically when the Desktop application launches.
"""

from .controller import SarthiController, SendResult, is_valid_query
from .pet import DesktopPet, attach_pet_to  # optional desktop pet

__all__ = ["SarthiController", "SendResult", "is_valid_query", "DesktopPet", "attach_pet_to"]
