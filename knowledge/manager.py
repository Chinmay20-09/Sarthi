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
from typing import Dict, List, Optional, Any

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
        applications_path: Optional[Path] = None,
        websites_path: Optional[Path] = None,
        devices_path: Optional[Path] = None,
        contacts_path: Optional[Path] = None,
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
        self._applications_cache: Optional[List[Dict]] = None
        self._websites_cache: Optional[List[Dict]] = None
        self._devices_cache: Optional[List[Dict]] = None
        self._contacts_cache: Optional[List[Dict]] = None

    def _load_knowledge_base(self, loader: KnowledgeLoader) -> List[Dict]:
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

    def load_applications(self) -> List[Dict]:
        """
        Load all discovered applications.

        Returns:
            List of application dictionaries
        """
        if self._applications_cache is not None:
            return self._applications_cache

        self._applications_cache = self._load_knowledge_base(self._app_loader)
        logger.info(f"Loaded {len(self._applications_cache)} applications")
        return self._applications_cache

    def load_websites(self) -> List[Dict]:
        """Load all websites."""
        if self._websites_cache is not None:
            return self._websites_cache

        self._websites_cache = self._load_knowledge_base(self._website_loader)
        logger.info(f"Loaded {len(self._websites_cache)} websites")
        return self._websites_cache

    def load_devices(self) -> List[Dict]:
        """Load all devices."""
        if self._devices_cache is not None:
            return self._devices_cache

        self._devices_cache = self._load_knowledge_base(self._device_loader)
        logger.info(f"Loaded {len(self._devices_cache)} devices")
        return self._devices_cache

    def load_contacts(self) -> List[Dict]:
        """Load all contacts."""
        if self._contacts_cache is not None:
            return self._contacts_cache

        self._contacts_cache = self._load_knowledge_base(self._contact_loader)
        logger.info(f"Loaded {len(self._contacts_cache)} contacts")
        return self._contacts_cache

    def get_all_entities(self) -> List[Dict]:
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

    def find_entity(self, query: str, category: Optional[str] = None) -> Optional[Dict]:
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

    def find_by_alias(self, alias: str, category: Optional[str] = None) -> Optional[Dict]:
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

    def find_application(self, name: str) -> Optional[Dict]:
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

    def find_website(self, name: str) -> Optional[Dict]:
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

    def save_applications(self, applications: List[Dict]) -> bool:
        """
        Save applications to knowledge base.

        Called by scanner after discovering applications.

        Args:
            applications: List of application dicts

        Returns:
            True if successful
        """
        from datetime import datetime

        data = {
            "version": 1,
            "last_scan": datetime.now().isoformat(),
            "entities": sorted(applications, key=lambda x: x.get("name", "").lower()),
        }

        success = self._app_loader.save(data)

        if success:
            # Invalidate cache
            self._applications_cache = None
            logger.info(f"Saved {len(applications)} applications")

        return success

    def save_websites(self, websites: List[Dict]) -> bool:
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

        Returns:
            True if successful
        """
        try:
            from scanner.app_scanner import scan_all

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
        logger.debug("Knowledge cache cleared")


# Global singleton instance
_manager: Optional[KnowledgeManager] = None


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
