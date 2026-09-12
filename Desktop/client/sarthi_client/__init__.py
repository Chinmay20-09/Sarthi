"""sarthi_client — the Sarthi Desktop client.

A thin Windows client for the Sarthi Backend. It contains NO assistant
intelligence: it sends the user's query to the Backend API over HTTP and
displays the response. All processing (model, interpreter, brain,
knowledge, skills, executor) lives in Backend/.
"""

from .controller import SarthiController, SendResult, is_valid_query

__all__ = ["SarthiController", "SendResult", "is_valid_query"]
