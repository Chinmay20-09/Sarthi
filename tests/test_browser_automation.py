"""
Tests for the DOM-aware browser automation module (v1.7).

Covers the reusable element resolver (BeautifulSoup analysis + Selenium
locators — no coordinate guessing), the verified copy/paste actions, chain
state, dynamic-DOM handling, and a full copy-on-A -> paste-on-B integration
chain. All browser interaction is mocked: ``_SoupDriver`` serves canned HTML
and resolves XPaths over a BeautifulSoup parse, so no real browser is needed.
"""

import re

import pytest
from skills.automation_engine.ai_chain.browser_automation import (
    AmbiguousElementError,
    BrowserAutomation,
    ChainState,
    ResolveError,
    find_candidates,
    parse_target,
    resolve_element,
    run_browser_chain,
    score_candidates,
)

# ----------------------------------------------------------------------
# Fake Selenium driver (serves HTML, resolves XPaths over bs4)
# ----------------------------------------------------------------------


class _NoSuchElementError(Exception):
    pass


def _eval_simple_xpath(soup, xpath):
    """Subset of XPath produced by browser_automation:
    ``//*[@id="x"]``, ``(//tag)[n]`` and absolute ``/html/body/tag[n]`` paths.
    """
    if xpath.startswith("//*["):
        match = re.match(r'^//\*\[@([\w-]+)="([^"]*)"\]$', xpath)
        if match:
            attr, value = match.groups()
            for el in soup.find_all(True):
                if str(el.get(attr, "")) == value:
                    return el
        return None
    match = re.match(r"^\(//([\w-]+)\)\[(\d+)\]$", xpath)
    if match:
        tag, index = match.group(1), int(match.group(2))
        elements = soup.find_all(tag)
        return elements[index - 1] if 1 <= index <= len(elements) else None
    parts = [p for p in xpath.split("/") if p]
    current = soup
    for part in parts:
        match = re.match(r"^([\w-]+)(?:\[(\d+)\])?$", part)
        if not match:
            return None
        tag = match.group(1)
        index = int(match.group(2) or 1)
        children = (
            current.find_all(tag, recursive=False) if current is not soup else current.find_all(tag)
        )
        if index < 1 or index > len(children):
            return None
        current = children[index - 1]
    return current


class _FakeElement:
    """Selenium WebElement stand-in wrapping a bs4 Tag.

    Field values live on the driver (``_values`` keyed by the tag's
    document-order position) so a fresh element instance for the same tag
    sees what earlier instances typed — the way a real browser works even
    though each lookup re-parses the HTML.
    """

    def __init__(self, driver, tag):
        self._driver = driver
        self._tag = tag
        self.clicked = False

    @property
    def tag_name(self):
        return self._tag.name

    def _key(self):
        return self._driver._tag_key(self._tag)

    @property
    def text(self):
        stored = self._driver._values.get(self._key())
        if stored is not None:
            return stored
        return self._tag.get_text(" ", strip=True)

    def get_attribute(self, name):
        if name in ("innerText", "textContent"):
            return self.text
        if name == "value":
            stored = self._driver._values.get(self._key())
            if stored is not None:
                return stored
            raw = self._tag.get("value")
            return str(raw) if raw is not None else None
        raw = self._tag.get(name)
        return str(raw) if raw is not None else None

    def click(self):
        self.clicked = True
        self._driver._on_click(self)

    def send_keys(self, *keys):
        if self._driver.block_writes:
            return
        value = "".join(str(k) for k in keys)
        key = self._key()
        if self.tag_name in ("input", "textarea"):
            self._driver._values[key] = self._driver._values.get(key, "") + value
        else:
            current = self._driver._values.get(key, self._tag.get_text(" ", strip=True))
            self._driver._values[key] = current + value
        self._driver.typed.append((self, value))

    def clear(self):
        self._driver._values[self._key()] = ""

    def set_value(self, value):  # used by the JS-insertion retry in tests
        if not self._driver.block_writes:
            self._driver._values[self._key()] = value


class _SoupDriver:
    """Selenium webdriver stand-in: pages dict, bs4-backed find_element."""

    def __init__(self, html="", pages=None, clipboard="", clipboard_after_click=None):
        self._pages = dict(pages or {})
        self.current_url = (
            next(iter(self._pages), "https://example.com/") if not html else "https://example.com/"
        )
        self._html = html or self._pages.get(self.current_url, "")
        self.clipboard = clipboard
        self.clipboard_after_click = clipboard_after_click
        self.block_writes = False
        self.clicked: list[_FakeElement] = []
        self.typed: list[tuple[_FakeElement, str]] = []
        self.scripts: list[tuple] = []
        self.async_calls: list[str] = []
        self._values: dict[int, str] = {}

    @property
    def page_source(self):
        return self._html

    def set_html(self, html):
        self._html = html

    def get(self, url):
        self.current_url = url
        self._html = self._pages.get(url, "")

    def _tag_key(self, tag):
        """Stable key for a tag: its absolute XPath in the current HTML.

        The same HTML re-parsed yields the same XPath, so values typed by
        one element instance are visible to a later instance for the same
        element.
        """
        parts: list[str] = []
        node = tag
        while node is not None and getattr(node, "name", None) and node.name != "[document]":
            parent = node.parent
            name = node.name
            if parent is not None:
                siblings = [c for c in parent.children if getattr(c, "name", None) == name]
                index = siblings.index(node) + 1 if siblings else 1
            else:
                index = 1
            parts.append(f"{name}[{index}]")
            node = parent
        return "/" + "/".join(reversed(parts))

    def find_element(self, by, value):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(self._html, "html.parser")
        tag = _eval_simple_xpath(soup, value)
        if tag is None:
            raise _NoSuchElementError(f"{by}: {value}")
        return _FakeElement(self, tag)

    def execute_script(self, script, *args):
        self.scripts.append((script, args))
        if "readyState" in script:
            return "complete"
        if "dispatchEvent(new Event('input'" in script and args:
            element = args[0]
            if isinstance(element, _FakeElement):
                element.set_value(args[1])
                return args[1]
        return None

    def execute_async_script(self, script, *args):
        self.async_calls.append(script)
        return self.clipboard

    def quit(self):
        pass

    def _on_click(self, element):
        self.clicked.append(element)
        if self.clipboard_after_click is not None and element.tag_name == "button":
            self.clipboard = self.clipboard_after_click


# ----------------------------------------------------------------------
# Element discovery (tests 1-6 from the request)
# ----------------------------------------------------------------------


class TestElementDiscovery:
    def test_find_button_by_exact_text(self):
        resolved = resolve_element(_SoupDriver(html="<button>Copy</button>"), "click", "Copy")
        assert resolved.element is not None
        assert resolved.candidate.text == "Copy"
        assert resolved.candidate.tag == "button"

    def test_find_button_by_aria_label(self):
        html = '<button aria-label="Copy">copy</button>'
        resolved = resolve_element(_SoupDriver(html=html), "click", "Copy")
        assert resolved.candidate.semantics["aria_label"] == "Copy"
        assert resolved.element is not None

    def test_find_input_by_placeholder(self):
        html = '<input placeholder="Paste value here">'
        resolved = resolve_element(_SoupDriver(html=html), "type", "Paste value here")
        assert resolved.candidate.semantics["placeholder"] == "Paste value here"
        assert resolved.element.get_attribute("placeholder") == "Paste value here"

    def test_find_input_by_name(self):
        resolved = resolve_element(_SoupDriver(html='<input name="username">'), "type", "username")
        assert resolved.candidate.semantics["name"] == "username"
        assert resolved.element.get_attribute("name") == "username"

    def test_find_textarea(self):
        html = "<textarea placeholder='Message'></textarea>"
        resolved = resolve_element(_SoupDriver(html=html), "type", "textarea")
        assert resolved.candidate.tag == "textarea"
        assert resolved.element.tag_name == "textarea"

    def test_find_contenteditable_element(self):
        html = '<div contenteditable="true" role="textbox"></div>'
        resolved = resolve_element(_SoupDriver(html=html), "type", "contenteditable")
        assert resolved.candidate.tag == "div"
        assert resolved.candidate.semantics["contenteditable"] == "true"

    def test_find_by_associated_label(self):
        html = '<label for="email">Email address</label><input id="email">'
        resolved = resolve_element(_SoupDriver(html=html), "type", "email")
        assert resolved.candidate.semantics["id"] == "email"

    def test_find_by_data_attribute(self):
        html = '<button data-testid="copy-button">x</button>'
        resolved = resolve_element(_SoupDriver(html=html), "click", "copy")
        assert "data-testid" in resolved.reason

    def test_action_filters_candidates(self):
        """Inputs are clickable AND typeable; plain spans are neither."""
        html = "<button>Copy</button><input placeholder='name'><span>plain</span>"
        clicks = find_candidates(html, "click", "copy")
        types = find_candidates(html, "type", "name")
        assert [c.tag for c in clicks] == ["button", "input"]
        assert [c.tag for c in types] == ["input"]

    def test_parse_target_drops_stopwords_keeps_content(self):
        spec = parse_target("find the copy button please")
        assert spec.keywords == ("copy", "button")
        assert parse_target("Paste value here").keywords == ("paste", "value", "here")


# ----------------------------------------------------------------------
# Multiple matches, ambiguity, unsafe matches (tests 7-8)
# ----------------------------------------------------------------------


class TestMultipleAndAmbiguous:
    def test_multiple_buttons_pick_best(self):
        html = '<button>Copy</button><button aria-label="Copy" title="Copy">Copy</button>'
        resolved = resolve_element(_SoupDriver(html=html), "click", "Copy button")
        # The richer candidate (aria-label + title + text) beats the bare one.
        assert "aria-label" in resolved.reason
        assert resolved.candidate.xpath.endswith("button[2]")

    def test_multiple_buttons_are_scored_not_first_match(self):
        html = '<button class="btn">Save</button><button id="save-main">Save</button>'
        resolved = resolve_element(_SoupDriver(html=html), "click", "Save")
        assert resolved.candidate.semantics["id"] == "save-main"  # id exact beat class

    def test_ambiguous_buttons_rejected_strict(self):
        html = "<button>Save</button><button>Save</button>"
        with pytest.raises(AmbiguousElementError, match="Ambiguous"):
            resolve_element(_SoupDriver(html=html), "click", "Save")

    def test_ambiguous_picks_first_when_not_strict(self):
        html = "<button>Save</button><button>Save</button>"
        resolved = resolve_element(_SoupDriver(html=html), "click", "Save", strict=False)
        assert resolved.candidate.index == 1  # document order tie-break

    def test_unsafe_generic_match_rejected(self):
        html = '<div><span class="btn">random</span></div>'
        with pytest.raises(ResolveError, match="No confident match"):
            resolve_element(_SoupDriver(html=html), "click", "Submit")

    def test_scoring_is_pure_and_reversible(self):
        html = '<button aria-label="Copy">Copy</button><button>Copy code</button>'
        ranked = score_candidates(find_candidates(html, "click", "copy"), "copy", "click")
        assert len(ranked) == 2
        assert ranked[0].score >= ranked[1].score


# ----------------------------------------------------------------------
# Copy operation (test 9)
# ----------------------------------------------------------------------


class TestCopyOperation:
    def test_copy_via_clipboard_button(self):
        driver = _SoupDriver(
            html='<button aria-label="Copy">Copy</button>', clipboard_after_click="ABC-123"
        )
        automation = BrowserAutomation(driver)
        value = automation.copy("Copy", key="code")
        assert value == "ABC-123"
        assert automation.state.clipboard == "ABC-123"
        assert automation.state.extracted_values["code"] == "ABC-123"
        assert driver.clicked  # the semantic button was clicked, not a pixel

    def test_copy_prefers_dom_value_over_clipboard(self):
        driver = _SoupDriver(html='<input id="code" value="ABC-123" readonly>')
        automation = BrowserAutomation(driver)
        value = automation.copy("code", key="value")
        assert value == "ABC-123"
        assert automation.state.clipboard == "ABC-123"
        assert driver.clipboard == ""  # the physical clipboard was never touched
        assert driver.async_calls == []  # clipboard was never read

    def test_copy_explicit_clipboard_workflow(self):
        driver = _SoupDriver(
            html='<input id="code" value="ABC-123"><button aria-label="Copy">Copy</button>',
            clipboard_after_click="XYZ-999",
        )
        automation = BrowserAutomation(driver)
        # use_clipboard=True forces the button path even though the DOM has a value.
        value = automation.copy("Copy", key="value", use_clipboard=True)
        assert value == "XYZ-999"
        assert driver.async_calls  # clipboard was read

    def test_copy_failure_raises_when_nothing_to_copy(self):
        driver = _SoupDriver(html="<p>nothing here</p>")
        automation = BrowserAutomation(driver)
        with pytest.raises(RuntimeError, match="Copy not verified"):
            automation.copy("Copy")


# ----------------------------------------------------------------------
# Paste operation (test 10)
# ----------------------------------------------------------------------


class TestPasteOperation:
    def test_paste_into_input_verified(self):
        driver = _SoupDriver(html='<input placeholder="Paste value here">')
        automation = BrowserAutomation(driver)
        assert automation.paste("Paste value here", "ABC-123") is True
        field = driver.find_element("xpath", "//input")
        assert field.get_attribute("value") == "ABC-123"
        assert automation.state.last_action == "paste"

    def test_paste_into_textarea_verified(self):
        driver = _SoupDriver(html="<textarea></textarea>")
        automation = BrowserAutomation(driver)
        assert automation.paste("textarea", "hello") is True
        assert driver.typed

    def test_paste_into_contenteditable_verified(self):
        driver = _SoupDriver(html='<div contenteditable="true" role="textbox"></div>')
        automation = BrowserAutomation(driver)
        assert automation.paste("contenteditable", "hello") is True

    def test_paste_js_retry_when_send_keys_rejected(self, monkeypatch):
        driver = _SoupDriver(html='<input placeholder="Paste value here">')
        automation = BrowserAutomation(driver)
        # The page ignores Selenium's typing; the JS insertion retry must
        # still land the value and pass verification.
        monkeypatch.setattr(BrowserAutomation, "_insert", lambda self, el, value: None)
        assert automation.paste("Paste value here", "ABC-123") is True
        assert any("dispatchEvent(new Event('input'" in script for script, _ in driver.scripts)

    def test_paste_failure_raises_when_field_never_accepts(self):
        driver = _SoupDriver(html='<input placeholder="Paste value here">')
        driver.block_writes = True
        automation = BrowserAutomation(driver)
        with pytest.raises(RuntimeError, match="Paste not verified"):
            automation.paste("Paste value here", "ABC-123")


# ----------------------------------------------------------------------
# Dynamic pages + re-resolution (tests 11-12)
# ----------------------------------------------------------------------


class TestDynamicDom:
    def test_reresolve_after_navigation(self):
        pages = {
            "https://a.example.com/": '<button aria-label="Copy">Copy</button>',
            "https://b.example.com/": '<input placeholder="Paste value here">',
        }
        driver = _SoupDriver(pages=pages)
        automation = BrowserAutomation(driver)
        automation.navigate("https://a.example.com/", wait=0)
        first = automation.resolve("click", "Copy")
        assert first.candidate.tag == "button"
        automation.navigate("https://b.example.com/", wait=0)
        second = automation.resolve("type", "Paste value here")
        assert second.candidate.tag == "input"
        assert second.locator != first.locator  # a fresh element on the new page

    def test_reresolve_after_dom_change(self):
        driver = _SoupDriver(html='<button id="open">Open</button>')
        automation = BrowserAutomation(driver)
        automation.click("Open")
        # A modal appears: the DOM changed entirely, so the next resolution
        # must inspect the NEW page, not the stale snapshot.
        driver.set_html('<input name="email" placeholder="Email">')
        resolved = automation.resolve("type", "email")
        assert resolved.element.get_attribute("name") == "email"

    def test_resolve_uses_fresh_page_source_every_call(self):
        driver = _SoupDriver(html="<button>First</button>")
        automation = BrowserAutomation(driver)
        automation.resolve("click", "First")
        driver.set_html("<button>Second</button>")
        with pytest.raises(ResolveError, match="No confident match"):
            automation.resolve("click", "First")
        second = automation.resolve("click", "Second")
        assert second.candidate.text == "Second"


# ----------------------------------------------------------------------
# No random coordinate clicking (test 13)
# ----------------------------------------------------------------------


class TestNoCoordinateClicking:
    def test_resolver_never_uses_screen_coordinates(self):
        driver = _SoupDriver(html='<button aria-label="Copy">Copy</button>')
        resolved = resolve_element(driver, "click", "Copy button")
        by, locator = resolved.locator
        assert by == "xpath"  # a DOM locator, never an (x, y) pixel point
        assert not re.search(r"\(\d+\s*,\s*\d+\)", locator)
        resolved.element.click()
        assert driver.clicked  # the interaction went through the live element

    def test_module_never_imports_pyautogui_or_random(self):
        import inspect

        from skills.automation_engine.ai_chain import browser_automation

        source = inspect.getsource(browser_automation)
        assert "import pyautogui" not in source.lower()
        assert "import random" not in source.lower()

    def test_scan_grid_disabled_for_html_discovery(self, monkeypatch):
        from skills.automation_engine.ai_chain import registry

        monkeypatch.delenv("AI_CHAIN_COORDINATE_SCAN", raising=False)
        assert registry.coordinate_scan_enabled() is False

    def test_regex_fallback_parser_still_never_clicks_coordinates(self, monkeypatch):
        import skills.automation_engine.ai_chain.browser_automation as ba

        monkeypatch.setattr(ba, "_bs4_available", lambda: False)
        driver = _SoupDriver(html='<button aria-label="Copy">Copy</button>')
        resolved = ba.resolve_element(driver, "click", "Copy")
        assert resolved.element is not None
        assert resolved.locator[0] == "xpath"


# ----------------------------------------------------------------------
# Chain state + integration (Website A -> Website B)
# ----------------------------------------------------------------------


class TestChainState:
    def test_initial_state(self):
        state = ChainState()
        assert state.clipboard is None
        assert state.extracted_values == {}
        assert state.current_url is None
        assert state.last_action is None


class TestIntegrationChain:
    def test_copy_on_site_a_paste_on_site_b(self):
        """The full example from the request:

        Website A: <button aria-label="Copy">Copy</button>
            ↓ copy/extract value
        Website B: <input placeholder="Paste value here">
            ↓ paste
            ↓ verify value
        """
        pages = {
            "https://a.example.com/": '<button aria-label="Copy">Copy</button>',
            "https://b.example.com/": '<input placeholder="Paste value here">',
        }
        driver = _SoupDriver(pages=pages, clipboard_after_click="ABC-123")
        result = run_browser_chain(
            [
                {"action": "open", "url": "https://a.example.com/", "wait": 0},
                {"action": "copy", "target": "Copy", "key": "value"},
                {"action": "open", "url": "https://b.example.com/", "wait": 0},
                {"action": "paste", "target": "Paste value here", "value": "$value"},
            ],
            driver=driver,
        )
        assert result.success, result.message
        assert len(result.steps) == 4
        assert all(step.ok for step in result.steps)
        # Chain state carried the value between websites — no physical
        # clipboard dependence for the hand-off.
        assert result.state.clipboard == "ABC-123"
        assert result.state.extracted_values["value"] == "ABC-123"
        assert result.state.current_url == "https://b.example.com/"
        # The pasted value actually landed in the destination field.
        field = driver.find_element("xpath", "//input")
        assert field.get_attribute("value") == "ABC-123"

    def test_chain_stops_at_first_failure(self):
        driver = _SoupDriver(html="<p>no button here</p>")
        result = run_browser_chain(
            [
                {"action": "open", "url": "https://a.example.com/", "wait": 0},
                {"action": "copy", "target": "Copy", "key": "value"},
                {"action": "open", "url": "https://b.example.com/", "wait": 0},
            ],
            driver=driver,
        )
        assert result.success is False
        assert result.steps[0].ok is True
        assert result.steps[1].ok is False
        assert len(result.steps) == 2  # stopped at the failing copy

    def test_unknown_action_reported(self):
        driver = _SoupDriver(html="<p>x</p>")
        result = run_browser_chain([{"action": "dance", "target": "everything"}], driver=driver)
        assert result.success is False
        assert "unknown action" in result.steps[0].error
