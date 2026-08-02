from skills.browser.models import (
    BrowserPage,
    BrowserSelection,
    BrowserSession,
)


class BrowserCache:
    def __init__(self):
        self._session = BrowserSession()

    def set_current_page(self, page: BrowserPage):
        self._session.current_page = page

    def get_current_page(self):
        return self._session.current_page

    def set_selection(self, selection: BrowserSelection):
        self._session.selected_text = selection

    def get_selection(self):
        return self._session.selected_text

    def get_session(self):
        return self._session

    def clear(self):
        self._session = BrowserSession()


browser_cache = BrowserCache()
