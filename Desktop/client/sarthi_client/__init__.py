"""sarthi_client — the Sarthi Desktop client.

The client handles explicit single-app launches locally from device-owned
inventory. Other interpretation and model work goes through the Backend API
over HTTP. The client does not import backend packages.

The desktop pet (optional) is available via :py:mod:`pet` and starts
auto-matically when the Desktop application launches.
"""

from .controller import SarthiController, SendResult, is_valid_query
from .pet import DesktopPet, attach_pet_to  # optional desktop pet

__all__ = ["SarthiController", "SendResult", "is_valid_query", "DesktopPet", "attach_pet_to"]
