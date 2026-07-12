# Sarthi Knowledge Base Architecture

## Overview

Sarthi now uses a **scalable, dynamic knowledge base system** instead of hardcoded application definitions. The knowledge base is the single source of truth for all discoverable entities: applications, websites, devices, contacts, plugins, and IoT devices.

## Architecture Components

### 1. Scanner (`scanner/app_scanner.py`)

The **scanner** automatically discovers installed applications from standard Windows locations and generates the knowledge base.

#### Scan Locations

- `C:\Program Files`
- `C:\Program Files (x86)`
- `%LOCALAPPDATA%\Programs`
- Windows Start Menu (current user)
- Windows Start Menu (all users)
- Every directory in `PATH` environment variable

#### File Types Discovered

- `.exe` executables
- `.lnk` shortcuts (with target resolution)

#### Key Functions

```python
# Scan specific locations
scan_program_files()           # C:\Program Files
scan_program_files_x86()       # C:\Program Files (x86)
scan_local_programs()          # %LOCALAPPDATA%\Programs
scan_start_menu()              # Windows Start Menu
scan_path()                    # PATH directories

# Main pipeline
registry = scan_all(output_path)  # Returns Dict[str, Application]
```

#### Alias Generation

Aliases are automatically generated using:

1. **Metadata dictionary** - Manual overrides for well-known apps
2. **Display name extraction** - From Windows file properties
3. **Smart variations** - Abbreviations, word combinations, etc.

Example:

```
Code.exe
  ↓
Visual Studio Code (display name)
  ↓
Aliases: ["code", "vscode", "vs code", "visual studio code"]
```

#### Duplicate Handling

When the same application is discovered multiple times, the scanner keeps only one copy using this preference order:

1. Program Files
2. Program Files (x86)
3. LocalAppData
4. Start Menu
5. PATH

### 2. Knowledge Loader (`knowledge/loader.py`)

The **loader** manages the application registry and provides a simple API for accessing discovered applications.

#### Key Classes

```python
# ApplicationRegistry - Manages the knowledge base
registry = ApplicationRegistry(Path("knowledge/applications.json"))

# Load applications (cached)
apps = registry.load_applications()  # Dict[str, Dict]

# Get individual app
app = registry.get_application("Visual Studio Code")

# Find by alias
app = registry.find_by_alias("vscode")

# Get aliases for app
aliases = registry.get_aliases_for_app("Visual Studio Code")

# Refresh (rescan and regenerate)
registry.refresh_applications()
```

#### Module-level API

For convenience, module-level functions are provided:

```python
from knowledge.loader import (
    load_applications,           # Load all apps
    refresh_applications,        # Rescan and regenerate
    find_application,           # Find by name
    find_by_alias,              # Find by alias
)

# Load applications
apps = load_applications()

# Find by alias
app = find_by_alias("vscode")
if app:
    print(f"Path: {app['path']}")
    print(f"Aliases: {app['aliases']}")

# Refresh when needed
find_by_alias.refresh_applications()
```

### 3. Knowledge Base Format (`knowledge/applications.json`)

The registry is stored as a well-formed JSON file with deterministic ordering:

```json
{
  "version": 1,
  "last_scan": "2026-07-07T15:56:28.942767",
  "applications": [
    {
      "name": "Visual Studio Code",
      "aliases": [
        "code",
        "visual studio code",
        "vs code",
        "vscode"
      ],
      "path": "C:\\Users\\...\\Code.exe"
    },
    ...
  ]
}
```

**Properties:**

- `version`: Schema version (future compatibility)
- `last_scan`: ISO 8601 timestamp of last scan
- `applications`: Sorted list of applications
  - `name`: Display name
  - `aliases`: List of alternative names (lowercase)
  - `path`: Full path to executable

### 4. Entity Resolver Integration (`brain/entity_resolver.py`)

The **entity resolver** now loads applications from the knowledge base and uses them for entity resolution:

```python
from brain.entity_resolver import EntityResolver

# Load with knowledge base (default: True)
resolver = EntityResolver(use_knowledge_base=True)

# Resolve text to entity
result = resolver.resolve("open visual studio code")
# Result: "open Code"
```

The resolver combines:

- **1040+ discovered applications** from the knowledge base
- **Remaining vocabulary** (websites, system commands)
- **Fuzzy matching** with alias detection

### 5. Application Executor (`actions/apps.py`)

The **app executor** now uses the knowledge base to launch applications:

```python
from actions.apps import open_app

# Open by name or alias
open_app("vscode")              # ✓ Works
open_app("visual studio code")  # ✓ Works
open_app("Code")                # ✓ Works
```

## Workflow

### 1. Initial Setup

```bash
# Scanner auto-runs and generates applications.json
python -m scanner.app_scanner
# Result: knowledge/applications.json with 1000+ applications
```

### 2. Normal Operation

```python
# Load applications (cached in memory)
from knowledge.loader import load_applications
apps = load_applications()

# Resolve entity
from brain.entity_resolver import EntityResolver
resolver = EntityResolver()
result = resolver.resolve("open chrome")

# Launch application
from actions.apps import open_app
open_app(result)
```

### 3. Refresh (Manual Rescan)

```python
from knowledge.loader import refresh_applications
refresh_applications()
# Re-scans system and regenerates applications.json
```

## Performance Characteristics

### Caching

- Applications are loaded once and cached in memory
- Subsequent calls return cached data
- Registry is reloaded only when explicitly refreshed

### Disk I/O

- First load: Read JSON from disk (~1000+ applications)
- Subsequent calls: Memory lookup only
- Refresh: Full system scan + write JSON

### Execution Time

- Initial scan: 10-15 seconds (one-time)
- Normal operation: <1ms lookup
- Entity resolution: <10ms with fuzzy matching

## Future Extensibility

The architecture is designed to support future entity types without code changes:

```
knowledge/
├── applications.json    # Applications
├── websites.json        # Websites (future)
├── devices.json         # Devices (future)
├── contacts.json        # Contacts (future)
├── plugins.json         # Plugins (future)
└── loader.py            # Generic loader
```

Each entity type follows the same format:

```json
{
  "version": 1,
  "last_scan": "ISO_TIMESTAMP",
  "entities": [
    {
      "name": "Name",
      "aliases": ["alias1", "alias2"],
      ...
    }
  ]
}
```

The Entity Resolver can consume all knowledge bases without modification.

## Error Handling

The system gracefully handles:

- **Missing registry**: Returns empty dict, logs warning
- **Corrupted JSON**: Returns empty dict, logs error
- **Permission errors**: Skips inaccessible locations, continues scanning
- **Broken shortcuts**: Skips unresolvable .lnk files
- **Invalid executables**: Skips files that don't exist
- **Missing pywin32**: Falls back to basic name extraction

## Best Practices

### 1. Loading Applications

```python
# ✓ Good - Load once at startup
apps = load_applications()

# ✗ Bad - Don't reload repeatedly
for i in range(1000):
    apps = load_applications()  # Wasteful
```

### 2. Finding Applications

```python
# ✓ Good - Use module-level API
from knowledge.loader import find_by_alias
app = find_by_alias("vscode")

# ✓ Also good - Use registry instance
from knowledge.loader import get_registry
registry = get_registry()
app = registry.find_by_alias("vscode")
```

### 3. Refreshing

```python
# ✓ Good - Refresh when needed (e.g., after app installation)
from knowledge.loader import refresh_applications
refresh_applications()

# ✗ Bad - Don't refresh on every operation
for command in user_commands:
    refresh_applications()  # Wasteful
```

## Configuration

No configuration file needed. The system works out of the box.

### Customization

To add custom aliases or improve alias generation, edit `APP_METADATA` in `scanner/app_scanner.py`:

```python
APP_METADATA = {
    "code": {
        "display_name": "Visual Studio Code",
        "aliases": ["vs code", "vscode", "visual studio code"],
    },
    # Add more...
}
```

## Debugging

Enable debug logging to see scanner details:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from scanner.app_scanner import scan_all
registry = scan_all()
```

Or run the scanner directly:

```bash
python -m scanner.app_scanner
```

## Migration from Hardcoded System

### Old System

```python
# Old: Hardcoded vocabulary
VOCABULARY = {
    "applications": ["chrome", "vscode", "notepad"],
    ...
}

APP_ALIASES = {
    "vscode": {"command": "code", "aliases": ["vs code", ...]}
}
```

### New System

```python
# New: Dynamic knowledge base
from knowledge.loader import load_applications, find_by_alias

apps = load_applications()
vscode = find_by_alias("vscode")
```

## Summary

| Aspect            | Old         | New              |
| ----------------- | ----------- | ---------------- |
| **Applications**  | 3 hardcoded | 1000+ discovered |
| **Aliases**       | Manual list | Auto-generated   |
| **Discovery**     | None        | Auto-scan        |
| **Scalability**   | Poor        | Excellent        |
| **Maintenance**   | High        | Low              |
| **Extensibility** | Limited     | Unlimited        |

---

**Status**: Production-ready

**Last Updated**: 2026-07-07

**Supported Platforms**: Windows (extensible to macOS/Linux)
