# Knowledge (observed)

Knowledge is what Sarthi knows about its available capabilities — in the
canonical model: skills, tools, capabilities, providers, hands, supported
entities and the relationships between them. It is distinct from Memory
(private user context) and from what a connected Hand currently provides.

**Implemented scope today:** the knowledge layer is the deterministic fact
base for apps and websites (entities + alias resolution). Skills and tools
are registered in code (`skills/registry.py`, `hermes/tool_registry.py`) and
Desktop capabilities are declared in `hands/desktop/capabilities.py` — there
is **no unified capability registry** in the knowledge layer, and no
known-vs-available separation from a live Hand. That registry and discovery
mechanism are PLANNED (see ARCHITECTURE.md "Canonical terminology map").

## Components

| Component | Location | Purpose |
| --- | --- | --- |
| KnowledgeManager | `knowledge/manager.py` | `get_manager()` singleton; loads both stores, CRUD, category/favourites management, `find_application`, `add_website` |
| EntityResolver | `knowledge/entity_resolver.py` | rapidfuzz matching of spoken names → canonical names; used by BrainEngine step 3 and the Hermes retriever |
| Loader / cache | `knowledge/loader.py`, `knowledge/cache.py` | JSON loading + caching |
| Memory | `knowledge/memory.py` | long-term /remember facts (see MEMORY.md) |

## Stores

### applications.json

- **Location**: `Backend/knowledge/applications.json`
- **Shape**: application entities with name, path, aliases, category
  (favourite/ignored/unattended states tracked via the scanner + categorize API).
- **Writers**: scanner skill (`skills/scanner/main.py`), /applications/categorize,
  /applications/run flow; **readers**: AppLauncherSkill, EntityResolver,
  Hermes retriever.

### websites.json

- **Location**: `Backend/knowledge/websites.json`
- **Shape**: website entities with URL + aliases.
- **Writers**: `/websites/search-and-save` (the "search on browser" fallback
  remembers the site so the next open goes direct — api.py:582-620);
  **readers**: BrowserSkill, EntityResolver, retriever.

## Data flow

```
"open yt" ─▶ BrowserSkill ─▶ KnowledgeManager.find_website("yt")
                              └─ alias match ─▶ https://youtube.com ─▶ webbrowser.open
```

```
BrainEngine step 3 ─▶ EntityResolver.resolve(target)
                       └─ fuzzy vs entities ─▶ canonical name (context.resolved=True)
```

## Related registries (kept distinct)

- The `browser_profiles` SQLite table (persistent Chrome profiles for
  browser awareness) is NOT knowledge data — owned by `database/profiles.py`.
- `knowledge_memory` (user facts) is memory, not app/site knowledge —
  see MEMORY.md. Knowledge is NOT the capability registry, and Memory is
  NOT a store of what Sarthi can do.
- Skills (skills/registry.py), Hermes tools (hermes/tool_registry.py) and
  Desktop capabilities (hands/desktop/capabilities.py) live in their own
  registries — not in the knowledge store.

## Tests

test_knowledge_manager, test_resolver_matching, test_resolve,
test_pipeline_compatibility (scanner→knowledge→resolver boundary),
test_scanner.
