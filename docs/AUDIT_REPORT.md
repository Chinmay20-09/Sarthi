> ⚠️ **Historical document.** This is the record of the August 2026 audit
> and the fixes it drove. The current compatibility audit lives at
> [`AUDIT_REPORT.md`](../AUDIT_REPORT.md) (repo root) — read that one
> first. Numbers below reflect the state at the time of writing.

# Sarthi Codebase Audit Report
**Date:** August 14, 2026  
**Status:** Comprehensive audit completed with critical fixes applied

---

## Executive Summary

A full codebase audit was conducted to identify outdated, dead, and broken code. **3 critical issues** were found and fixed. The system now has improved cleanliness and maintainability.

**Tests Status:** ✅ All 209 tests passing

---

## Critical Issues Fixed ✅

### 1. **Import Ordering Bug in api.py** (HIGH)
**Status:** ✅ FIXED

**Issue:** Import and router registration were placed AFTER the `if __name__ == "__main__"` block (lines 273-275), making them unreachable when api.py is imported as a module.

**Fix Applied:**
- Moved `from skills.browser.routes import router as browser_router` to imports section (line 36)
- Moved `app.include_router(browser_router)` to app configuration section (line 51)
- Removed duplicate code after `if __name__` block

**Impact:** API can now be properly imported as a module without losing browser routes.

---

### 2. **Duplicate Skill Discovery Systems** (HIGH)
**Status:** ✅ PARTIALLY FIXED - Consolidation recommended

**Issue:** Two parallel skill loading systems existed:
- `skills/manager.py` - Old system with `load_skills()` and `load_skill_instances()`
- `skills/registry.py` - New system with `SkillRegistry` class

Both were being used in different parts of the codebase.

**Fixes Applied:**
- Updated `skills/automation_engine/skill.py` to import SKILLS_DIR from canonical `config.py` instead of `skills/manager.py`
- Confirmed `brain/engine.py` and `api.py` use the new `registry.py` system

**Recommendation:** 
- Keep `skills/registry.py` as canonical system (already used by BrainEngine)
- Document that `skills/manager.py` is for backward compatibility only
- Consider deprecation timeline for full removal in v2.0

---

### 3. **Duplicate Resolver Shims** (HIGH)
**Status:** ✅ FIXED

**Issue:** Two identical backward-compatibility shims existed:
- `brain/resolver.py` - Re-exported EntityResolver
- `brain/entity_resolver.py` - Also re-exported EntityResolver

Both pointed to `knowledge/entity_resolver.py` as canonical location.

**Fixes Applied:**
- Removed duplicate `brain/resolver.py` 
- Updated `brain/engine.py` to import from `brain/entity_resolver.py`
- Updated `tests/test_brain_engine.py` to import from `brain/entity_resolver.py`
- Kept `brain/entity_resolver.py` as the maintained backward-compatibility shim

**Impact:** Reduced redundant code paths, clearer import chain.

---

## Additional Issues Fixed ✅

### 4. **Debug Print Statements** (LOW)
**Status:** ✅ FIXED

**File:** `speech/speech_to_text.py`

**Changes:**
- Line 71-72: Replaced `print(f"Language: {info.language}")` with `logger.debug(...)`
- Line 72: Replaced `print(f"Probability: {info.language_probability:.2f}")` with `logger.debug(...)`
- Line 77: Replaced `print(segment.text)` with `logger.debug(segment.text)`

**Impact:** Professional logging instead of debug prints. Respects logging configuration.

---

### 5. **Orphaned Files Removed** (MEDIUM)
**Status:** ✅ FIXED

**Files Deleted:**
- `brain/resolver.py` - Duplicate shim (consolidation with entity_resolver.py)
- `models/intent.py` - Orphaned Intent model (canonical: brain/intent.py)
- `knowledge/scanners/application_scanner.py` - Duplicate shim (consolidation with knowledge/scanners/__init__.py)

**Verification:** Grep verified no files import these deleted modules.

---

## Outstanding Issues Requiring Attention

### 1. **Deprecated Module - brain/normalizer.py** (HIGH)
**Status:** ✅ RESOLVED — removed in the September 2026 cleanup

**Issue:** Entire module deprecated in favor of `brain/interpreter.py`. Generated DeprecationWarnings on every test run.

**Resolution:**
- Removed `brain/normalizer.py`
- Removed `tests/test_normalizer.py` (it tested deprecated code only)
- Deprecation warnings are gone; use `brain.interpreter.interpret()` for new code

---

### 2. **Deprecated Package - actions/** (MEDIUM)
**Status:** ✅ RESOLVED — package removed in the September 2026 cleanup

**Issue:** Entire `actions/` package was deprecated. Architecture has moved to the skill-based system.

**Files Removed:** 
- `actions/apps.py` - Shim for `skills/app_launcher/`
- `actions/browser.py` - Shim for `skills/browser/`
- `actions/files.py` - Incomplete stub
- `actions/system.py` - Incomplete stub

**Resolution:**
- Removed the whole package; use skills or BrainEngine:
  ```python
  # NEW (recommended)
  from brain.engine import BrainEngine
  engine = BrainEngine()
  response = engine.process("open Chrome")
  ```

---

### 3. **Brain/schemas.py** (LOW)
**Status:** ✅ RESOLVED — removed in the September 2026 cleanup

**Issue:** Was a single re-export of Intent from brain.intent.py

**Resolution:** Removed; import `Intent` directly from `brain.intent`

---

### 4. **Incomplete Implementations** (MEDIUM)
**Status:** 📋 NEEDS RESOLUTION

| File | Issue | Recommendation |
|------|-------|-----------------|
| `brain/planner.py` | Pass-through stub only. Comment says "Future: split compound commands" | Implement or document as future work |
| `actions/files.py` | Complete stub: "Future: Create, read, write..." | ✅ Removed with `actions/` |
| `actions/system.py` | Complete stub: "Future: Shutdown, restart..." | ✅ Removed with `actions/` |
| `skills/automation_engine/preview.py` | Marked "Status: Stub" | Complete or remove |

---

### 5. **Missing Directory Error Handling** (MEDIUM)
**Status:** ⚠️ NEEDS FIX

**File:** `api.py` line 52

**Issue:** Static files mount assumes `UI/` directory exists:
```python
app.mount("/ui", StaticFiles(directory="UI"), name="ui")
```

**Recommendation:** Add error handling:
```python
from pathlib import Path
if Path("UI").exists():
    app.mount("/ui", StaticFiles(directory="UI"), name="ui")
else:
    logger.warning("UI directory not found - static files not mounted")
```

---

## Files Reviewed and Status

### ✅ Clean/Well-Maintained
- `brain/engine.py` - Proper architecture, good documentation
- `brain/executor.py` - Well-structured handler dispatch system
- `brain/interpreter.py` - Clear NLP pipeline
- `brain/intent.py` - Well-designed Intent model
- `brain/context.py` - Good context management
- `brain/response.py` - Proper response structure
- `brain/entity_resolver.py` - Maintained backward-compat shim
- `skills/registry.py` - Well-designed plugin system
- `skills/base.py` - Clear BaseSkill interface
- `knowledge/entity_resolver.py` - Canonical resolver location
- `knowledge/router.py` - Good routing logic
- `utils/logger.py` - Proper logging setup
- `database/manager.py` - Clean database interface
- `events/bus.py` - Good event system

### ✅ Removed in Later Cleanup
- `brain/normalizer.py` - Deprecated → removed (September 2026)
- `actions/` package - Deprecated shims → removed (September 2026)

### 🔧 Incomplete/Stubs
- `brain/planner.py` - Pass-through only
- `skills/automation_engine/preview.py` - Stub

---

## Code Quality Improvements Made

| Change | Impact | Status |
|--------|--------|--------|
| Fixed import ordering in api.py | API now properly importable | ✅ FIXED |
| Consolidate resolver shims | Clearer dependency chain | ✅ FIXED |
| Remove duplicate scanner shim | Reduce code duplication | ✅ FIXED |
| Replace debug print with logging | Professional logging, respects config | ✅ FIXED |
| Standardize SKILLS_DIR imports | Use canonical config module | ✅ FIXED |

---

## Test Coverage

**Before Audit:** 209 passing tests  
**After Audit:** 209 passing tests ✅  
**Since (September 2026):** 549+ passing tests, 0 deprecation warnings

No regressions introduced by changes.

---

## Recommended Action Plan

### Immediate (This Sprint)
- [x] Remove `brain/normalizer.py` and `tests/test_normalizer.py` — done
- [ ] Add error handling for missing `UI/` directory in `api.py` — still open
- [ ] Review and decide: Keep or implement `brain/planner.py` — still open

### Short-term (Next Sprint)
- [x] Remove `actions/files.py` and `actions/system.py` stubs — done (package removed)
- [x] Update internal imports to avoid `skills/manager.py` — done (module removed)
- [x] Document API changes required for removing `actions/` package — done

### Long-term (v2.0 Planning)
- [x] Remove entire `actions/` package — done
- [x] Remove all backward-compat shims — done
- [ ] Migrate all imports to canonical locations — in progress

---

## Migration Guide for Developers

**DO:**
```python
# ✅ Recommended
from brain.engine import BrainEngine
from skills.registry import get_registry
from knowledge.entity_resolver import EntityResolver
```

**DON'T:**
```python
# ❌ Removed — use the canonical imports above
from actions.apps import open_app
from brain.resolver import EntityResolver
from brain.normalizer import normalize
from skills.manager import load_skill_instances
```

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Critical Issues Fixed | 3 |
| Medium Issues Fixed | 2 |
| Low Issues Fixed | 1 |
| Outstanding High-Priority Issues | 0 |
| Outstanding Medium-Priority Issues | 1 |
| Files Deleted | 3 |
| Files Modified | 5 |
| Test Coverage Maintained | ✅ 100% |
| Deprecation Warnings Remaining | 21 (from deprecated normalizer.py) |

---

**Audit Completed:** August 14, 2026  
**Next Audit Recommended:** Before v2.0 release
