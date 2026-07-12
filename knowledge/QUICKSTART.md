# Windows Application Scanner - Quick Start Guide

## One-Minute Setup

### 1. Install Dependencies (if needed)
```bash
pip install pywin32
```

### 2. Run Scanner
```bash
python -m knowledge.scanner
```

### 3. Check Results
- Open: `knowledge/applications.json`
- Contains: 88+ applications + games
- Updated: Every time you run the scanner

## What It Does

Discovers and catalogs all:
- **Start Menu Applications** from Windows shortcuts
- **Games** from configurable directories (Steam, Epic, GOG, etc.)
- **Executables** across your system

## Quick Commands

### Run Scan
```bash
cd C:\Sarthi
python -m knowledge.scanner
```

### Use in Python
```python
from knowledge.scanner import WindowsApplicationScanner

scanner = WindowsApplicationScanner()
result = scanner.scan()
print(result['statistics'])
```

### Add Game Directory
```python
from knowledge.config import ScannerConfig
ScannerConfig.add_game_directory("D:\\MyGames")
scanner = WindowsApplicationScanner()
scanner.scan()
```

## Output Format

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
      "name": "Game Title",
      "aliases": [],
      "path": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Game\\game.exe",
      "category": "game"
    }
  ]
}
```

## Files

- **`knowledge/scanner.py`**: Main scanner (431 lines)
- **`knowledge/config.py`**: Configuration (69 lines)
- **`knowledge/applications.json`**: Results
- **`knowledge/SCANNER_README.md`**: Full documentation
- **`knowledge/IMPLEMENTATION_NOTES.md`**: Technical details

## Key Features

✓ Scans Windows Start Menu shortcuts (.lnk)
✓ Recursively scans game directories
✓ Resolves shortcuts to executables
✓ Deduplicates by path
✓ Generates JSON output
✓ Clear statistics and logging
✓ Modular, well-documented code

## Example Output

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

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No applications found | Check Start Menu folder permissions |
| Shortcuts not resolving | Install pywin32: `pip install pywin32` |
| Permission errors | Run as Administrator |
| No game folders found | Verify paths in `knowledge/config.py` |

## Configuration

Edit `knowledge/config.py` to:
- Add game directories: `add_game_directory(Path(...))`
- Change recursion depth: `MAX_RECURSION_DEPTH`
- Modify extensions: `EXECUTABLE_EXTENSIONS`

## Performance

Typical scan times:
- Start Menu: < 1 second
- Game directories: 1-5 seconds
- Total: 2-6 seconds

## Next Steps

1. Run the scanner: `python -m knowledge.scanner`
2. Check the output: Open `knowledge/applications.json`
3. Use the data in Sarthi's knowledge system
4. Schedule periodic scans to keep data fresh

---

For detailed documentation, see:
- `SCANNER_README.md` - Full documentation
- `IMPLEMENTATION_NOTES.md` - Technical details
