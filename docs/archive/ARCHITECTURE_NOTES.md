# Sarthi Architecture - Post-Audit Notes

> ℹ️ **Superseded.** The canonical architecture document is now
> [`ARCHITECTURE.md`](../ARCHITECTURE.md) at the repo root. This file remains
> as a valid migration/reference record (canonical imports, removed modules);
> its test counts and skill lists reflect an earlier date.

## System Overview

Sarthi is a Desktop AI Assistant built with a layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI / API Layer                          │
│                    (main.py, api.py)                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Brain Pipeline                           │
│         (interpreter → planner → resolver → executor)       │
│                   (brain/engine.py)                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│         Skills Layer (Plugin-Based Architecture)            │
│         • AppLauncher | Browser | ProjectTracker |          │
│         • AutomationEngine | Scanner | Speech | etc.        │
│                 (skills/*.py via registry)                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│           Knowledge & Database Layer                        │
│      • Entity Resolution | Routing | Caching | Storage      │
│     (knowledge/*.py, database/*.py, events/*.py)            │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### Brain Pipeline (`brain/`)

**canonical imports:**

```python
from brain.engine import BrainEngine  # Main entry point
from brain.intent import Intent       # Intent model
from knowledge.entity_resolver import EntityResolver  # Canonical location
```

**Flow:**

1. **Interpreter** (`interpreter.py`) - Parse text → Intent
2. **Planner** (`planner.py`) - Multi-step plan generation
3. **Resolver** (`entity_resolver.py`) - Fuzzy entity matching
4. **Executor** (`executor.py`) - Dispatch intents to handlers
5. **Engine** (`engine.py`) - Orchestrates full pipeline (public API)

### Skills System (`skills/`)

**canonical imports:**

```python
from skills.registry import get_registry, SkillRegistry
from skills.base import BaseSkill
```

**Architecture:**

- **registry.py** - CANONICAL skill discovery & management system
  - Discovers skills from manifest.json files
  - Instantiates skill classes dynamically
  - Manages skill lifecycle (enable, disable, list)
  
- **manager.py** - REMOVED (September 2026) — legacy loader superseded by `registry.py`

**Available Skills:**

- `app_launcher/` - Launch desktop applications
- `browser/` - Open/search known websites in the default browser
- `browser_awareness/` - Inspect arbitrary websites (Playwright) with validated actions
- `project_tracker/` - Track software projects (GitHub)
- `automation_engine/` - AI-chain laptop automation & assistant generation
- `scanner/` - Application discovery
- `speech/` - Speech recognition features
- `user_config/` - Configuration management
- `personal_context/` - Personal profile fields (safe, field-scoped access)
- `natural_language_processor/` - Conversational fallback via Hermes (registered last)

### Knowledge Layer (`knowledge/`)

**Entity Resolution:**

```python
from knowledge.entity_resolver import EntityResolver
```

**Components:**

- **entity_resolver.py** - CANONICAL entity resolution
- **manager.py** - Knowledge graph management + application refresh
- **loader.py** - Pure JSON I/O
- **cache.py** - TTL caching for knowledge data
- **memory.py** - Conversation memory and preferences
- **scanner integration** - Application discovery lives in `skills/scanner/`

### Database Layer (`database/`)

```python
from database.manager import DatabaseManager
```

- SQLite-based persistence
- Schema management
- CRUD operations for applications, projects, and config

### Events System (`events/`)

```python
from events import get_bus
bus = get_bus()
bus.publish("event_name", {data}, source="module")
bus.subscribe("event_name", callback)
```

- Decoupled communication between modules
- Event history tracking
- Source attribution

---

## Cleaned Up Code

### ✅ Removed (September 2026 cleanup)

All modules scheduled for removal have been deleted from the codebase:

- `brain/normalizer.py` + `tests/test_normalizer.py` — use `brain.interpreter.interpret()`
- `actions/` package (`apps.py`, `browser.py`, `files.py`, `system.py`) — skills replace these
- `brain/entity_resolver.py` — import from `knowledge.entity_resolver`
- `brain/schemas.py` — import from `brain.intent`
- `knowledge/scanners/` — application discovery now lives in `skills/scanner/`
- `skills/manager.py` — use `skills/registry.py`

---

## Recent Audit Fixes (August 14, 2026)

### 🔴 Critical Issues Fixed

1. **api.py Import Ordering** - FIXED
   - Problem: Imports after `if __name__ == "__main__"` (unreachable)
   - Solution: Moved imports to top, router registration to setup

2. **Duplicate Resolver Shims** - FIXED
   - Problem: Both `brain/resolver.py` and `brain/entity_resolver.py` existed
   - Solution: Removed `brain/resolver.py`, kept `entity_resolver.py`

3. **Skill Discovery Duplication** - FIXED
   - Problem: Both `manager.py` and `registry.py` systems used
   - Solution: Confirmed `registry.py` as canonical, updated imports

### 🟠 Additional Fixes

1. **Debug Prints Removed** - FIXED
   - File: `speech/speech_to_text.py`
   - Solution: Replaced print() with logger.debug()

2. **Orphaned Files Deleted** - FIXED
   - `models/intent.py` - Duplicate of `brain/intent.py`
   - `knowledge/scanners/application_scanner.py` - Duplicate shim

3. **Import Dependencies Fixed** - FIXED
   - `skills/automation_engine/skill.py` - Import from config instead of manager

---

## Recommended Import Patterns

### ✅ DO USE (Canonical Locations)

```python
# Brain Pipeline
from brain.engine import BrainEngine
from brain.intent import Intent
from brain.interpreter import interpret

# Skills
from skills.registry import get_registry
from skills.base import BaseSkill

# Knowledge
from knowledge.entity_resolver import EntityResolver
from knowledge.manager import get_manager

# Database
from database.manager import DatabaseManager

# Events
from events import get_bus

# Configuration
from config import SKILLS_DIR, WHISPER_MODEL, API_PORT
```

### ❌ DON'T USE (Deprecated)

The shims below were removed in the September 2026 cleanup — don't
reintroduce them. Use the canonical imports from the DO list above.

```python
# ❌ Removed — import from knowledge.entity_resolver
from brain.resolver import EntityResolver
from brain.entity_resolver import EntityResolver

# ❌ Removed — use skills.registry instead
from skills.manager import load_skill_instances

# ❌ Removed — use skills instead
from actions.apps import open_app
from actions.browser import open_site
from brain.normalizer import normalize
from knowledge.scanners import scan_all
```

---

## Common Patterns

### Processing Natural Language Commands

```python
from brain.engine import BrainEngine

engine = BrainEngine()  # Auto-loads all skills
response = engine.process("open Chrome")

if response.success:
    print(f"Action: {response.intent.action}")
    print(f"Target: {response.intent.target}")
    print(f"Result: {response.action_result}")
    print(f"Time: {response.execution_ms}ms")
else:
    print(f"Error: {response.error}")
```

### Discovering and Using Skills

```python
from skills.registry import get_registry

registry = get_registry()

# List all skills
for meta in registry.list_skills():
    print(f"{meta['name']} v{meta['version']}")

# Get specific skill
app_launcher = registry.get_skill("app_launcher")

# Get all skill instances
all_skills = registry.get_all_instances()
```

### Publishing Events

```python
from events import get_bus

bus = get_bus()

# Publish an event
bus.publish("user_action", {
    "action": "opened_browser",
    "url": "github.com"
}, source="user_handler")

# Subscribe to events
def on_startup(event):
    print(f"System started at {event.timestamp}")

bus.subscribe("system_startup", on_startup)
```

### Resolving Entity Names

```python
from knowledge.entity_resolver import EntityResolver

resolver = EntityResolver(entities=[
    {"name": "Chrome", "aliases": ["google chrome", "chrome browser"]},
    {"name": "Firefox", "aliases": ["firefox browser"]},
])

resolved = resolver.resolve("chrome browser")
# Returns: "Chrome"
```

---

## Configuration

All configuration in `config.py`:

```python
from config import (
    SKILLS_DIR,           # Path to skills directory
    WHISPER_MODEL,        # Speech model size
    WHISPER_DEVICE,       # GPU/CPU device
    API_HOST, API_PORT,   # API server settings
    LOG_LEVEL,            # Logging verbosity
)
```

---

## Testing

### Run All Tests

```bash
python -m pytest tests/ -v
```

### Run Specific Module Tests

```bash
python -m pytest tests/test_brain_engine.py -v
python -m pytest tests/test_executor.py -v
python -m pytest tests/test_skill_base.py -v
```

### Current Test Status

- ✅ 549+ tests passing
- ✅ No deprecation warnings (`brain/normalizer.py` removed)
- ✅ No regressions

---

## Next Steps for v2.0

1. **Remove Deprecated Modules** — ✅ done (September 2026)
   - [x] `brain/normalizer.py` + `tests/test_normalizer.py`
   - [x] `actions/` package (files.py, system.py)

2. **Remove Backward-Compat Shims** — ✅ done
   - [x] `brain/entity_resolver.py` → import from `knowledge/`
   - [x] `brain/schemas.py` → import from `brain/intent.py`
   - [x] `knowledge/scanners/` → use `skills/scanner/`

3. **Consolidate Skill Systems** — ✅ done
   - [x] Removed `skills/manager.py` (only `registry.py` remains)

4. **Architecture Improvements** (open)
   - [ ] Implement proper multi-step planner in `brain/planner.py`
   - [ ] Add comprehensive API documentation

---

**Last Updated:** September 3, 2026  
**Status:** Post-Audit — deprecated modules removed, docs refreshed  
**Next Review:** Before v2.0 release
