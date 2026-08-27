"""
KnowledgeManager - Centralized knowledge system for Sarthi.

THE SINGLE SOURCE OF TRUTH for all entity knowledge.

Manages:
- Applications
- Websites (future)
- Devices (future)
- Contacts (future)
- Plugins (future)

This is the ONLY place that should be imported by:
- EntityResolver
- AppExecutor
- BrowserSkill
- Any skill that needs entity data

Nobody should import knowledge.loader directly.
"""

import logging
from pathlib import Path
from typing import Any

from knowledge.loader import KnowledgeLoader

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """
    Centralized knowledge management system.

    Responsibilities:
    - Load all knowledge bases (JSON files)
    - Search and find entities
    - Merge entities from multiple sources
    - Generate aliases
    - Coordinate with scanner for refresh
    - Maintain cache

    Design:
    - Dependency injection from upper layers
    - Pure data operations
    - No HTTP/network calls
    - Stateless searches
    """

    def __init__(
        self,
        applications_path: Path | None = None,
        websites_path: Path | None = None,
        devices_path: Path | None = None,
        contacts_path: Path | None = None,
    ):
        """
        Initialize Knowledge Manager.

        Args:
            applications_path: Path to applications.json
            websites_path: Path to websites.json (future)
            devices_path: Path to devices.json (future)
            contacts_path: Path to contacts.json (future)
        """
        # Set default paths
        knowledge_dir = Path(__file__).parent

        self.applications_path = applications_path or knowledge_dir / "applications.json"
        self.websites_path = websites_path or knowledge_dir / "websites.json"
        self.devices_path = devices_path or knowledge_dir / "devices.json"
        self.contacts_path = contacts_path or knowledge_dir / "contacts.json"

        # Loaders for each knowledge base
        self._app_loader = KnowledgeLoader(self.applications_path)
        self._website_loader = KnowledgeLoader(self.websites_path)
        self._device_loader = KnowledgeLoader(self.devices_path)
        self._contact_loader = KnowledgeLoader(self.contacts_path)

        # Cache
        self._applications_cache: list[dict] | None = None
        self._websites_cache: list[dict] | None = None
        self._devices_cache: list[dict] | None = None
        self._contacts_cache: list[dict] | None = None
        self._last_scan_cache: str | None = None
        self._last_scan_loaded = False

    # Valid application categories (user-driven classification)
    CATEGORY_STATUSES = ("favourite", "ignored", "unattended")

    # ------------------------------------------------------------------
    # Applications — categorized storage (favourite / ignored / unattended)
    # ------------------------------------------------------------------

    def _load_applications_data(self) -> dict[str, list[dict[str, Any]]]:
        """Load the categorized applications structure.

        Reads the new ``categories`` schema. Legacy files with a flat
        ``entities`` list are treated as all-unattended so the first-time
        categorization flow can classify them.
        """
        data = self._app_loader.load()
        if data is None:
            return {status: [] for status in self.CATEGORY_STATUSES}

        categories = data.get("categories")
        if isinstance(categories, dict):
            return {status: list(categories.get(status) or []) for status in self.CATEGORY_STATUSES}

        entities = data.get("entities", [])
        if not isinstance(entities, list):
            entities = []
        return {"favourite": [], "ignored": [], "unattended": list(entities)}

    def _save_applications_data(self, categories: dict[str, list[dict[str, Any]]]) -> bool:
        """Persist the categorized applications structure (version 2)."""
        from datetime import datetime

        data: dict[str, Any] = {
            "version": 2,
            "last_scan": datetime.now().isoformat(),
            "categories": {
                status: list(categories.get(status, [])) for status in self.CATEGORY_STATUSES
            },
        }

        success = self._app_loader.save(data)
        if success:
            self._applications_cache = None
            self._last_scan_cache = data["last_scan"]
            self._last_scan_loaded = True
        return success

    def _load_knowledge_base(self, loader: KnowledgeLoader) -> list[dict]:
        """
        Load entities from a knowledge base file.

        Args:
            loader: KnowledgeLoader instance

        Returns:
            List of entity dictionaries
        """
        data = loader.load()
        if data is None:
            return []

        if "entities" in data:
            return data["entities"]

        entities = []

        entities.extend(data.get("applications", []))
        entities.extend(data.get("games", []))
        entities.extend(data.get("websites", []))
        entities.extend(data.get("devices", []))
        entities.extend(data.get("contacts", []))

        return entities

    def load_applications(self) -> list[dict]:
        """
        Load all known applications across every category.

        Each app dict is stamped with its ``app_status``
        (favourite / ignored / unattended).

        Returns:
            List of application dictionaries
        """
        if self._applications_cache is not None:
            return self._applications_cache

        categories = self._load_applications_data()
        apps: list[dict[str, Any]] = []
        for status in self.CATEGORY_STATUSES:
            for app in categories.get(status, []):
                item = dict(app)
                item["app_status"] = status
                apps.append(item)

        self._applications_cache = apps
        logger.info(f"Loaded {len(apps)} applications")
        return apps

    def get_applications_by_status(self, status: str) -> list[dict[str, Any]]:
        """Get applications in a specific category.

        Uses the cached load_applications() data when available to avoid
        re-reading the JSON file from disk on every call.
        """
        if status not in self.CATEGORY_STATUSES:
            return []
        # Prefer the cached flat list (avoids a disk read)
        apps = self.load_applications()
        return [dict(app) for app in apps if app.get("app_status") == status]

    def categorize_application(self, name: str, status: str) -> dict[str, Any] | None:
        """
        Move an application to a new category by name.

        Args:
            name: Application name (case-insensitive)
            status: favourite, ignored, or unattended

        Returns:
            Updated app dict (with app_status), or None if not found
        """
        if status not in self.CATEGORY_STATUSES:
            logger.warning(f"Invalid application status: {status}")
            return None

        categories = self._load_applications_data()
        moved: dict[str, Any] | None = None

        for cat in self.CATEGORY_STATUSES:
            bucket = categories.get(cat, [])
            for app in list(bucket):
                if str(app.get("name", "")).lower() == name.lower():
                    bucket.remove(app)
                    moved = app
                    break
            if moved is not None:
                break

        if moved is None:
            return None

        categories.setdefault(status, []).append(moved)
        self._save_applications_data(categories)
        logger.info(f"Categorized '{name}' as {status}")
        return {**moved, "app_status": status}

    def load_websites(self) -> list[dict]:
        """Load all websites."""
        if self._websites_cache is not None:
            return self._websites_cache

        self._websites_cache = self._load_knowledge_base(self._website_loader)
        logger.info(f"Loaded {len(self._websites_cache)} websites")
        return self._websites_cache

    def load_devices(self) -> list[dict]:
        """Load all devices."""
        if self._devices_cache is not None:
            return self._devices_cache

        self._devices_cache = self._load_knowledge_base(self._device_loader)
        logger.info(f"Loaded {len(self._devices_cache)} devices")
        return self._devices_cache

    def load_contacts(self) -> list[dict]:
        """Load all contacts."""
        if self._contacts_cache is not None:
            return self._contacts_cache

        self._contacts_cache = self._load_knowledge_base(self._contact_loader)
        logger.info(f"Loaded {len(self._contacts_cache)} contacts")
        return self._contacts_cache

    def get_all_entities(self) -> list[dict]:
        """
        Get all entities across all types.

        Used by EntityResolver for fuzzy matching.

        Returns:
            List of all entities with normalized structure
        """
        entities = []

        # Add applications
        for app in self.load_applications():
            entity = {
                "name": app.get("name", ""),
                "aliases": app.get("aliases", []),
                "category": "applications",
                "path": app.get("path"),
            }
            entities.append(entity)

        # Add websites
        for website in self.load_websites():
            entity = {
                "name": website.get("name", ""),
                "aliases": website.get("aliases", []),
                "category": "websites",
                "url": website.get("url"),
            }
            entities.append(entity)

        # Add devices (future)
        for device in self.load_devices():
            entity = {
                "name": device.get("name", ""),
                "aliases": device.get("aliases", []),
                "category": "devices",
                "ip": device.get("ip"),
            }
            entities.append(entity)

        # Add contacts (future)
        for contact in self.load_contacts():
            entity = {
                "name": contact.get("name", ""),
                "aliases": contact.get("aliases", []),
                "category": "contacts",
                "phone": contact.get("phone"),
            }
            entities.append(entity)

        return entities

    def find_entity(self, query: str, category: str | None = None) -> dict | None:
        """
        Find entity by exact name match.

        Args:
            query: Entity name to search for
            category: Limit to specific category (optional)

        Returns:
            Entity dict or None
        """
        query_lower = query.lower()

        # Search applications
        if category is None or category == "applications":
            for app in self.load_applications():
                if app.get("name", "").lower() == query_lower:
                    return app

        # Search websites
        if category is None or category == "websites":
            for website in self.load_websites():
                if website.get("name", "").lower() == query_lower:
                    return website

        # Search devices
        if category is None or category == "devices":
            for device in self.load_devices():
                if device.get("name", "").lower() == query_lower:
                    return device

        # Search contacts
        if category is None or category == "contacts":
            for contact in self.load_contacts():
                if contact.get("name", "").lower() == query_lower:
                    return contact

        return None

    def find_by_alias(self, alias: str, category: str | None = None) -> dict | None:
        """
        Find entity by alias.

        Args:
            alias: Alias to search for
            category: Limit to specific category (optional)

        Returns:
            Entity dict or None
        """
        alias_lower = alias.lower()

        # Search applications
        if category is None or category == "applications":
            for app in self.load_applications():
                aliases = [a.lower() for a in app.get("aliases", [])]
                if alias_lower in aliases:
                    return app

        # Search websites
        if category is None or category == "websites":
            for website in self.load_websites():
                aliases = [a.lower() for a in website.get("aliases", [])]
                if alias_lower in aliases:
                    return website

        # Search devices
        if category is None or category == "devices":
            for device in self.load_devices():
                aliases = [a.lower() for a in device.get("aliases", [])]
                if alias_lower in aliases:
                    return device

        # Search contacts
        if category is None or category == "contacts":
            for contact in self.load_contacts():
                aliases = [a.lower() for a in contact.get("aliases", [])]
                if alias_lower in aliases:
                    return contact

        return None

    def find_application(self, name: str) -> dict | None:
        """
        Find application by name or alias.

        Convenience method for application lookups.

        Args:
            name: Application name or alias

        Returns:
            Application dict or None
        """
        # Try exact name first
        app = self.find_entity(name, category="applications")
        if app:
            return app

        # Try alias
        return self.find_by_alias(name, category="applications")

    def find_website(self, name: str) -> dict | None:
        """
        Find website by name or alias.

        Convenience method for website lookups.

        Args:
            name: Website name or alias

        Returns:
            Website dict or None
        """
        # Try exact name first
        website = self.find_entity(name, category="websites")
        if website:
            return website

        # Try alias
        return self.find_by_alias(name, category="websites")

    def merge_scan_results(self, applications: list[dict]) -> dict[str, Any]:
        """
        Merge freshly scanned apps into the categorized knowledge base.

        Apps that are already categorized (favourite/ignored/unattended)
        keep their status and get refreshed metadata. Brand-new apps land
        in ``unattended`` so the UI can prompt the user to categorize them.

        Args:
            applications: List of scanned application dicts

        Returns:
            Dict with success, new_unattended list, and total count
        """
        categories = self._load_applications_data()
        for status in self.CATEGORY_STATUSES:
            categories.setdefault(status, [])

        # Index existing apps by path (primary) and name (fallback)
        by_path: dict[str, tuple[str, dict[str, Any]]] = {}
        by_name: dict[str, tuple[str, dict[str, Any]]] = {}
        for cat in self.CATEGORY_STATUSES:
            for app in categories[cat]:
                path = str(app.get("path") or "").lower()
                if path:
                    by_path.setdefault(path, (cat, app))
                name = str(app.get("name") or "").lower()
                if name:
                    by_name.setdefault(name, (cat, app))

        new_unattended: list[dict[str, Any]] = []

        for app in applications:
            existing = by_path.get(str(app.get("path") or "").lower())
            if existing is None:
                existing = by_name.get(str(app.get("name") or "").lower())

            if existing is not None:
                # Keep the user's categorization; refresh metadata
                existing[1].update(app)
            else:
                new_unattended.append(dict(app))

        categories["unattended"] = categories["unattended"] + new_unattended
        self._save_applications_data(categories)

        logger.info(
            f"Merged {len(applications)} scanned apps; "
            f"{len(new_unattended)} new app(s) awaiting categorization"
        )
        return {
            "success": True,
            "new_unattended": new_unattended,
            "total": len(applications),
        }

    def save_applications(self, applications: list[dict]) -> bool:
        """
        Save scanned applications (backward-compatible).

        Delegates to merge_scan_results, which preserves user categories
        and places brand-new apps into ``unattended``.

        Args:
            applications: List of application dicts

        Returns:
            True if successful
        """
        return self.merge_scan_results(applications).get("success", False)

    def save_websites(self, websites: list[dict]) -> bool:
        """Save websites to knowledge base."""
        from datetime import datetime

        data = {
            "version": 1,
            "last_scan": datetime.now().isoformat(),
            "entities": sorted(websites, key=lambda x: x.get("name", "").lower()),
        }

        success = self._website_loader.save(data)

        if success:
            self._websites_cache = None
            logger.info(f"Saved {len(websites)} websites")

        return success

    def refresh_applications(self) -> bool:
        """
        Refresh applications by rescanning system.

        Delegates to the ScannerSkill for scanning.
        Knowledge does NOT orchestrate — it saves the results.

        Returns:
            True if successful
        """
        try:
            from skills.scanner.application_scanner import scan_all

            logger.info("Refreshing applications...")
            applications = scan_all()

            # Save via manager
            return self.save_applications(applications)

        except Exception as e:
            logger.error(f"Failed to refresh applications: {e}")
            return False

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._applications_cache = None
        self._websites_cache = None
        self._devices_cache = None
        self._contacts_cache = None
        self._last_scan_cache = None
        self._last_scan_loaded = False
        logger.debug("Knowledge cache cleared")

    @property
    def last_scan(self) -> str | None:
        """
        Timestamp of the most recent applications scan.

        Cached in memory and refreshed whenever applications are saved,
        so repeated reads never re-parse the knowledge base file.

        Returns:
            ISO-8601 timestamp string, or None if never scanned
        """
        if not self._last_scan_loaded:
            data = self._app_loader.load()
            self._last_scan_cache = data.get("last_scan") if isinstance(data, dict) else None
            self._last_scan_loaded = True
        return self._last_scan_cache


# Global singleton instance
_manager: KnowledgeManager | None = None


def get_manager() -> KnowledgeManager:
    """
    Get the global KnowledgeManager instance.

    Singleton pattern for efficiency.

    Returns:
        KnowledgeManager instance
    """
    global _manager

    if _manager is None:
        _manager = KnowledgeManager()

    return _manager
