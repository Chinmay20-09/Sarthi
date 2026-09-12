"""
Event Bus for Sarthi.

Decoupled communication between components through events.
Components publish events and subscribe to events without
knowing about each other directly.

Events:
    SpeechRecognized    — Voice command was transcribed
    IntentParsed        — Brain interpreted an intent
    SkillExecuted       — A skill completed execution
    KnowledgeUpdated    — Knowledge base was modified
    ProjectCreated      — New project was created
    ApplicationScanned  — Scanner completed a scan
"""

from .bus import Event, EventBus, get_bus

__all__ = ["EventBus", "Event", "get_bus"]
