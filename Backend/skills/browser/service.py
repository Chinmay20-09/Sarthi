from database.cache.browser_cache import browser_cache

from .models import BrowserAction, BrowserPage, BrowserSelection


class BrowserService:
    def receive_page(self, page: BrowserPage):
        browser_cache.set_current_page(page)
        return page

    def receive_selection(self, selection: BrowserSelection):
        browser_cache.set_selection(selection)
        return selection

    def get_current_page(self):
        return browser_cache.get_current_page()

    def get_selection(self):
        return browser_cache.get_selection()

    def get_session(self):
        return browser_cache.get_session()

    def execute_action(self, action: BrowserAction):
        # Placeholder until browser extension exists
        print(f"Browser Action Requested: {action}")
        return {"status": "pending", "action": action.action}


browser_service = BrowserService()
