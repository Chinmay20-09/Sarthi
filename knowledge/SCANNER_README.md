# Windows Application Scanner for Sarthi

A comprehensive Windows application and game discovery system that scans the Windows Start Menu and configurable game directories.

## Features

- **Start Menu Scanning**: Resolves .lnk shortcuts from both system and user Start Menu folders
- **Game Directory Scanning**: Recursively scans configurable game directories (Steam, Epic Games, GOG, etc.)
- **Smart Deduplication**: Eliminates duplicate entries by comparing resolved executable paths
- **COM API Integration**: Uses win32com.client to resolve shortcuts to their actual executables
- **Modular Design**: Separate functions for each scanning task
- **Comprehensive Logging**: Clear statistics showing discovery results

## Components

### `knowledge/config.py`

Configuration class for the scanner. Defines:

```python
ScannerConfig.GAME_DIRECTORIES       # Directories to scan
ScannerConfig.SYSTEM_START_MENU     # System Start Menu path
ScannerConfig.USER_START_MENU       # User Start Menu path
ScannerConfig.OUTPUT_FILE           # Output JSON file path
ScannerConfig.MAX_RECURSION_DEPTH   # Recursion depth limit
```

**Adding Custom Game Directories:**

```python
from knowledge.config import ScannerConfig
from pathlib import Path

ScannerConfig.add_game_directory(Path("C:\\MyGames"))
```

### `knowledge/scanner.py`

Main scanner class `WindowsApplicationScanner` with methods:

- `scan_start_menu()`: Scans Windows Start Menu shortcuts
- `scan_game_directories()`: Recursively scans game directories
- `_resolve_shortcut()`: Resolves .lnk files using COM API
- `_scan_directory()`: Recursively scans directories for executables
- `_process_executable()`: Processes found executables
- `deduplicate_applications()`: Deduplicates by executable path
- `save_applications()`: Saves results to JSON
- `scan()`: Main entry point that orchestrates the complete scan

## Output Format

Results are saved to `knowledge/applications.json`:

```json
{
  "version": "1.0",
  "last_scan": "2026-07-10T01:22:16.509915",
  "statistics": {
    "applications": 88,
    "games": 7,
    "shortcuts_resolved": 88,
    "duplicates_skipped": 0
  },
  "applications": [
    {
      "name": "Google Chrome",
      "aliases": [],
      "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "category": "application"
    }
  ],
  "games": [
    {
      "name": "Once a Pawn a King",
      "aliases": [],
      "path": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Once a Pawn a King Demo\\Once a Pawn a King.exe",
      "category": "game"
    }
  ]
}
```

## Usage

### Command Line

Run the scanner from command line:

```bash
python -m knowledge.scanner
```

Output:
```
============================================================
SCAN SUMMARY
============================================================
Applications: 88
Games: 7
Shortcuts Resolved: 88
Duplicates Skipped: 0
Total Unique Entries: 95
Output File: C:\Sarthi\knowledge\applications.json
============================================================
```

### As a Module

Use the scanner in your code:

```python
from knowledge.scanner import WindowsApplicationScanner

# Create scanner
scanner = WindowsApplicationScanner()

# Run scan
result = scanner.scan()

# Access results
print(f"Found {result['total_unique']} applications")
print(f"Statistics: {result['statistics']}")
```

### With Custom Output

```python
from knowledge.scanner import WindowsApplicationScanner
from pathlib import Path

scanner = WindowsApplicationScanner()
result = scanner.scan(output_file=Path("custom_location.json"))
```

## Scanning Details

### Start Menu Scanning

- Scans `C:\ProgramData\Microsoft\Windows\Start Menu\Programs` (system)
- Scans `%APPDATA%\Microsoft\Windows\Start Menu\Programs` (user)
- Resolves .lnk shortcuts to target executables
- Uses shortcut filename as application name
- Skips shortcuts with no valid targets

### Game Directory Scanning

Default directories:
- `C:\Program Files (x86)\Steam\steamapps\common` (Steam)
- `C:\Program Files\Epic Games` (Epic Games)
- `C:\GOG Games` (GOG)
- `%USERPROFILE%\Games`

Scans:
- .exe, .bat, .cmd, .com files
- Recursively up to MAX_RECURSION_DEPTH (default: 10)
- Skips hidden files/directories
- Uses filename (without extension) as application name

### Deduplication

- All paths normalized to lowercase
- Resolves symlinks and relative paths
- Keeps first occurrence if duplicates found
- Tracks duplicates in statistics

## Dependencies

- `win32com` (pywin32): For COM API shortcut resolution
  - Install: `pip install pywin32`
  - Configure: Run `python Scripts/pywin32_postinstall.py` as admin (if needed)

If `win32com` is not available:
- Scanner still works (skips shortcut resolution)
- Only game directories are scanned
- All .exe files are discovered directly

## Statistics

After each scan, the output contains:

```json
"statistics": {
  "applications": 88,        // Apps found from Start Menu
  "games": 7,               // Games found in game directories
  "shortcuts_resolved": 88, // Shortcuts successfully resolved
  "duplicates_skipped": 0   // Duplicate entries eliminated
}
```

## Logging

Set logging level to see detailed scan progress:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

scanner = WindowsApplicationScanner()
scanner.scan()
```

Output includes:
- Directories being scanned
- Shortcuts being resolved
- Duplicate detections
- Errors and permission issues

## Performance

Typical scan times:
- Start Menu: < 1 second (88+ applications)
- Game Directories: 1-5 seconds depending on directory size and disk speed
- Total: 2-6 seconds

## Customization

### Add Game Directory at Runtime

```python
from knowledge.config import ScannerConfig
from pathlib import Path

ScannerConfig.add_game_directory("D:\\Games")
scanner = WindowsApplicationScanner()
scanner.scan()
```

### Change Output Location

```python
from pathlib import Path
from knowledge.scanner import WindowsApplicationScanner

scanner = WindowsApplicationScanner()
scanner.scan(output_file=Path("my_apps.json"))
```

### Modify Scan Parameters

Edit `knowledge/config.py`:

```python
class ScannerConfig:
    GAME_DIRECTORIES = [
        Path("C:\\MyCustomGamePath"),
        # Add more directories...
    ]
    
    MAX_RECURSION_DEPTH = 15  # Increase recursion depth
```

## Error Handling

The scanner gracefully handles:
- Missing directories (skipped)
- Permission errors (logged, not fatal)
- Invalid shortcuts (skipped)
- Missing shortcut targets (skipped)
- Missing win32com library (skips shortcut resolution)

## Future Enhancements

Potential improvements:
- Support for .url (web shortcuts)
- Application metadata extraction (icons, descriptions)
- Registry scanning for uninstalled applications
- Performance optimization with caching
- Alias generation from application metadata
- Integration with application installer detection

## Troubleshooting

### No applications found

- Check Start Menu folder permissions
- Verify game directories exist and are readable
- Enable debug logging to see detailed errors

### Shortcuts not resolving

- Ensure pywin32 is installed: `pip install pywin32`
- May need admin privileges on some systems
- Check that shortcut targets exist

### Unicode errors

- Use UTF-8 encoding throughout
- Output file uses UTF-8 encoding explicitly

## Module Architecture

```
knowledge/
├── __init__.py
├── config.py           # Configuration
├── scanner.py          # Main scanner class
├── loader.py           # JSON I/O
├── manager.py          # Knowledge management
└── applications.json   # Scan results
```

The scanner is designed to be used with the existing Sarthi knowledge management system.
