# Sarthi Architecture - Post-Audit Notes

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
from brain.entity_resolver import EntityResolver  # Backward-compat shim
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
  
- **manager.py** - OLD system (deprecated, for backward compat only)
  - `load_skills()` - metadata loading
  - `load_skill_instances()` - dynamic instantiation
  - Status: Kept for backward compatibility, but not recommended for new code

**Available Skills:**
- `app_launcher/` - Launch desktop applications
- `browser/` - Open websites in browser
- `project_tracker/` - Track software projects
- `automation_engine/` - Code generation & automation
- `scanner/` - Application discovery
- `speech/` - Speech recognition features
- `user_config/` - Configuration management

### Knowledge Layer (`knowledge/`)

**Entity Resolution:**
```python
# Canonical location
from knowledge.entity_resolver import EntityResolver

# Backward-compat shim (deprecated)
from brain.entity_resolver import EntityResolver
```

**Components:**
- **entity_resolver.py** - CANONICAL entity resolution
- **manager.py** - Knowledge graph management
- **router.py** - Data source routing
- **memory.py** - Caching layer
- **writer.py** - Knowledge persistence
- **scanners/** - Backward-compat shim (deprecated)

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

## Deprecated/Legacy Code

### ❌ To Remove (High Priority)

#### 1. brain/normalizer.py
- **Status**: DEPRECATED - Use `brain.interpreter.interpret()` instead
- **Reason**: Duplicate fuzzy matching now in interpreter
- **Impact**: Creates 21 deprecation warnings in test suite
- **Action**: Remove this file and `tests/test_normalizer.py`

#### 2. actions/ package
- **Status**: DEPRECATED - Use BrainEngine instead
- **Reason**: Architecture moved to skill-based system
- **Contents**:
  - `apps.py` - Shim for `skills/app_launcher/`
  - `browser.py` - Shim for `skills/browser/`
  - `files.py` - Incomplete stub
  - `system.py` - Incomplete stub
- **Action**: Plan removal for v2.0

### ⚠️ Backward-Compat Shims (Keep for Now)

#### 1. brain/entity_resolver.py
- Re-exports from `knowledge.entity_resolver`
- Used for backward compatibility
- Plan: Remove in v2.0

#### 2. brain/schemas.py
- Single re-export of Intent model
- Used in `brain/__init__.py`
- Plan: Remove in v2.0

#### 3. knowledge/scanners/__init__.py
- Re-exports from `skills/scanner/`
- Backward-compat shim
- Plan: Remove in v2.0

#### 4. skills/manager.py
- Old skill discovery system
- Kept for backward compatibility
- **Recommendation**: Use `skills/registry.py` instead
- Plan: Consolidate in next sprint

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

4. **Debug Prints Removed** - FIXED
   - File: `speech/speech_to_text.py`
   - Solution: Replaced print() with logger.debug()

5. **Orphaned Files Deleted** - FIXED
   - `models/intent.py` - Duplicate of `brain/intent.py`
   - `knowledge/scanners/application_scanner.py` - Duplicate shim

6. **Import Dependencies Fixed** - FIXED
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
from knowledge.router import DataSource

# Database
from database.manager import DatabaseManager

# Events
from events import get_bus

# Configuration
from config import SKILLS_DIR, WHISPER_MODEL, API_PORT
```

### ❌ DON'T USE (Deprecated)

```python
# ❌ Old brain resolver
from brain.resolver import EntityResolver  # Use brain.entity_resolver instead

# ❌ Old skill loading
from skills.manager import load_skill_instances  # Use registry instead

# ❌ Action executors
from actions.apps import open_app  # Use BrainEngine instead
from actions.browser import open_site  # Use BrainEngine instead

# ❌ Deprecated normalizer
from brain.normalizer import normalize  # Use brain.interpreter.interpret instead

# ❌ Deprecated scanners
from knowledge.scanners import scan_all  # Use skills.scanner instead
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
- ✅ 209 tests passing
- ⚠️ 21 deprecation warnings (from `brain/normalizer.py` - scheduled for removal)
- ✅ No regressions

---

## Next Steps for v2.0

1. **Remove Deprecated Modules**
   - [ ] `brain/normalizer.py`
   - [ ] `tests/test_normalizer.py`
   - [ ] `actions/` package (files.py, system.py)

2. **Remove Backward-Compat Shims**
   - [ ] `brain/entity_resolver.py` → import directly from `knowledge/`
   - [ ] `brain/schemas.py` → import directly from `brain/intent.py`
   - [ ] `knowledge/scanners/` → import directly from `skills/scanner/`

3. **Consolidate Skill Systems**
   - [ ] Remove `skills/manager.py` (keep only `registry.py`)
   - [ ] Update any remaining imports

4. **Architecture Improvements**
   - [ ] Implement proper multi-step planner in `brain/planner.py`
   - [ ] Refactor global state management (e.g., in `wakeword.py`)
   - [ ] Add comprehensive API documentation

---

**Last Updated:** August 14, 2026  
**Status:** Post-Audit (3 critical issues fixed, system stable)  
**Next Review:** Before v2.0 release
