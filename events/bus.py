"""
Event Bus for Sarthi.

Provides decoupled communication between components through events.
Any component can publish an event, and any component can subscribe.

ARCHITECTURE:
    The Event Bus allows:
    - Loose coupling between components
    - Easy addition of new event handlers
    - Centralized logging/monitoring of all events
    - Future multi-agent coordination

Usage:
    from events import get_bus

    bus = get_bus()

    # Subscribe to events
    @bus.on("knowledge_updated")
    def handle_update(event):
        print(f"Knowledge updated: {event.data}")

    # Publish events
    bus.publish("knowledge_updated", {"entity_type": "applications"})
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Type alias for event handler
EventHandler = Callable[["Event"], None]


@dataclass
class Event:
    """
    A single event in the system.

    Attributes:
        name: Event name (e.g., "speech_recognized", "skill_executed")
        data: Event-specific payload
        timestamp: When the event was created
        source: Optional source component name
    """

    name: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str | None = None

    def __repr__(self) -> str:
        return f"<Event '{self.name}' from {self.source or 'unknown'}>"


class EventBus:
    """
    Simple publish-subscribe event bus.

    Components can:
        - Publish events (any component)
        - Subscribe to events (any component)
        - Unsubscribe when no longer needed

    This is intentionally simple. No async, no persistence.
    Future enhancements can add:
        - Async handlers
        - Persistent event log
        - Event replay
        - Priority-based dispatch
    """

    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = {}
        self._history: list[Event] = []
        self._max_history = 100  # Keep last 100 events for debugging

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def on(self, event_name: str, handler: EventHandler | None = None):
        """
        Register an event handler.

        Can be used as a decorator or direct call:

        @bus.on("event_name")
        def handler(event):
            pass

        bus.on("event_name", handler)

        Args:
            event_name: Name of the event to subscribe to
            handler: Optional handler function. If None, returns a decorator.

        Returns:
            The handler function (for decorator support)
        """
        if handler is not None:
            if event_name not in self._handlers:
                self._handlers[event_name] = []
            self._handlers[event_name].append(handler)
            logger.debug(f"Handler registered for event '{event_name}'")
            return handler

        # Return decorator
        def decorator(fn: EventHandler) -> EventHandler:
            self.on(event_name, fn)
            return fn

        return decorator

    def off(self, event_name: str, handler: EventHandler) -> None:
        """
        Remove an event handler.

        Args:
            event_name: Name of the event
            handler: The handler function to remove
        """
        if event_name in self._handlers:
            self._handlers[event_name].remove(handler)
            if not self._handlers[event_name]:
                del self._handlers[event_name]
            logger.debug(f"Handler removed for event '{event_name}'")

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(
        self,
        event_name: str,
        data: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> Event:
        """
        Publish an event to all registered handlers.

        Args:
            event_name: Name of the event
            data: Event payload
            source: Source component name

        Returns:
            The Event object (for inspection)
        """
        event = Event(
            name=event_name,
            data=data or {},
            source=source,
        )

        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        # Dispatch to handlers
        handlers = self._handlers.get(event_name, [])
        wildcard_handlers = self._handlers.get("*", [])

        all_handlers = handlers + wildcard_handlers

        if not all_handlers:
            logger.debug(f"Event '{event_name}' published (no handlers)")
            return event

        for handler in all_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Handler failed for event '{event_name}': {e}")

        logger.debug(f"Event '{event_name}' dispatched to {len(all_handlers)} handler(s)")
        return event

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def history(self) -> list[Event]:
        """Recent event history (for debugging)."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()

    @property
    def handler_count(self) -> int:
        """Total number of registered handlers."""
        return sum(len(h) for h in self._handlers.values())

    # ------------------------------------------------------------------
    # Event name constants
    # ------------------------------------------------------------------

    # Speech
    SPEECH_RECOGNIZED = "speech_recognized"
    WAKE_WORD_DETECTED = "wake_word_detected"

    # Brain
    INTENT_PARSED = "intent_parsed"
    PLAN_CREATED = "plan_created"
    ENTITY_RESOLVED = "entity_resolved"

    # Skills
    SKILL_EXECUTING = "skill_executing"
    SKILL_EXECUTED = "skill_executed"
    SKILL_ERROR = "skill_error"
    SKILL_REGISTERED = "skill_registered"

    # Knowledge
    KNOWLEDGE_UPDATED = "knowledge_updated"
    KNOWLEDGE_LOADED = "knowledge_loaded"
    ENTITIES_REFRESHED = "entities_refreshed"

    # Scanner
    SCAN_STARTED = "scan_started"
    SCAN_COMPLETED = "scan_completed"

    # Projects
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"

    # System
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"


# Global singleton instance
_bus: EventBus | None = None


def get_bus() -> EventBus:
    """
    Get the global EventBus instance.

    Returns:
        EventBus singleton
    """
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
