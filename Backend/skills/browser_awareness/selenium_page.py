"""
skills/browser_awareness/selenium_page.py

Selenium adapter that speaks the small Playwright-ish page surface the
Browser Awareness loop needs (manager -> inspector/executor):

    page.goto(url)                        page.locator(sel).first
    page.inner_text(sel)                  locator.click / fill / select_option
    page.page_source / current_url        locator.check / uncheck / evaluate
    (title via page.title)                locator.count / locator / is_visible
                                          locator.scroll_into_view_if_needed

Only this module imports Selenium for the action path (and even here it
is imported lazily); the executor and manager keep working unchanged on
top of either this adapter or a real Playwright page. Every locator is
re-resolved at action time — the same semantics Playwright gives us —
so a re-render between snapshot and action cannot act on a stale
element. Explicit ``timeout=`` arguments are accepted and ignored:
Selenium has its own implicit-wait story and the executor's budget is
informational here.
"""

from __future__ import annotations

from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

_XPATH_PREFIX = "xpath="


class SeleniumPageAdapter:
    """A Selenium driver dressed as the Playwright page the loop expects."""

    def __init__(self, driver: Any):
        self._driver = driver

    # -- navigation -----------------------------------------------------

    def goto(self, url: str, timeout: int | None = None, wait_until: str | None = None) -> None:
        """Navigate (Selenium's get() blocks until the document loads)."""
        self._driver.get(url)

    # -- inspection hooks used by the BeautifulSoup inspector -----------

    @property
    def page_source(self) -> str:
        return self._driver.page_source

    def inner_text(self, selector: str) -> str:
        """Rendered text of the first element matching the CSS selector."""
        from selenium.webdriver.common.by import By

        try:
            element = self._driver.find_element(By.CSS_SELECTOR, selector)
            return element.text or ""
        except Exception as exc:  # pragma: no cover - live browser
            logger.debug(f"inner_text({selector}) failed: {exc}")
            return ""

    # -- executor surface -----------------------------------------------

    def locator(self, selector: str) -> SeleniumLocatorSet:
        return SeleniumLocatorSet(self._driver, selector)

    # Everything else (current_url, title, execute_script, window_handles,
    # switch_to, ...) passes straight through to the driver.
    def __getattr__(self, name: str):
        return getattr(self._driver, name)


class SeleniumLocatorSet:
    """Playwright's ``page.locator(...)`` shape — everything starts with ``.first``."""

    def __init__(self, driver: Any, selector: str):
        self._driver = driver
        self._selector = selector

    @property
    def first(self) -> SeleniumLocator:
        return SeleniumLocator(self._driver, self._selector)


class SeleniumLocator:
    """One lazily resolved element (Playwright locator semantics).

    ``element`` is set only for element-relative locators (the executor's
    ``locator("xpath=ancestor::form[1]")``) — resolution then starts from
    that element instead of the document.
    """

    def __init__(self, driver: Any, selector: str, element: Any = None):
        self._driver = driver
        self._selector = selector
        self._element = element

    # -- resolution ------------------------------------------------------

    def _find_all(self) -> list:
        from selenium.webdriver.common.by import By

        if self._element is not None:
            if self._selector.lower().startswith(_XPATH_PREFIX):
                value = self._selector[len(_XPATH_PREFIX) :]
                return list(self._element.find_elements(By.XPATH, value))
            return list(self._element.find_elements(By.CSS_SELECTOR, self._selector))
        if self._selector.lower().startswith(_XPATH_PREFIX):
            return list(self._driver.find_elements(By.XPATH, self._selector[len(_XPATH_PREFIX) :]))
        return list(self._driver.find_elements(By.CSS_SELECTOR, self._selector))

    def _resolve(self):
        matches = self._find_all()
        if not matches:
            raise RuntimeError(f"element not found: {self._selector}")
        return matches[0]

    # -- actions ---------------------------------------------------------

    def count(self) -> int:
        try:
            return len(self._find_all())
        except Exception:
            return 0

    def click(self, timeout: int | None = None) -> None:
        self._resolve().click()

    def fill(self, text: str, timeout: int | None = None) -> None:
        element = self._resolve()
        try:
            element.clear()
        except Exception:  # some editors refuse clear(); send_keys appends
            logger.debug(f"clear() refused for {self._selector}; typing over it")
        element.send_keys((text or "")[:5000])

    def select_option(self, value: str, timeout: int | None = None) -> None:
        from selenium.webdriver.support.ui import Select

        select = Select(self._resolve())
        try:
            select.select_by_value(value or "")
        except Exception:
            select.select_by_visible_text(value or "")

    def check(self, timeout: int | None = None) -> None:
        element = self._resolve()
        if not element.is_selected():
            element.click()

    def uncheck(self, timeout: int | None = None) -> None:
        element = self._resolve()
        if element.is_selected():
            element.click()

    def is_visible(self, timeout: int | None = None) -> bool:
        try:
            return bool(self._resolve().is_displayed())
        except Exception:
            return False

    def evaluate(self, script: str, *args) -> Any:
        """Run a Playwright-style ``(el) => ...`` arrow against the element."""
        element = self._resolve()
        return self._driver.execute_script(f"return ({script})(arguments[0]);", element, *args)

    def scroll_into_view_if_needed(self, timeout: int | None = None) -> None:
        self._driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", self._resolve()
        )

    def locator(self, selector: str) -> SeleniumLocator:
        """Element-relative locator (e.g. ``xpath=ancestor::form[1]``)."""
        return SeleniumLocator(self._driver, selector, element=self._resolve())
