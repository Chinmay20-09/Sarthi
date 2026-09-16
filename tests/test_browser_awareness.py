"""Tests for the Browser Awareness capability.

Everything is tested with pure logic, fake providers and fake browser
components — the suite never needs Playwright, Chrome or the local model.

Covers: snapshot building (caps/filters/sanitization), Hermes JSON
validation, the pure safety gate, selector allow-list, the manager
inspect -> observe -> validate -> execute -> reinspect loop (incl.
cleanup and confirmation halts), skill parsing + test-mode planning,
interpreter routing (URL sentences -> browse, known sites stay fast),
and the Brain 'browse' handler delegation.
"""

from pathlib import Path

import pytest
from brain.intent import Intent
from brain.interpreter import interpret, interpret_many
from skills.browser_awareness.page_snapshot import build_page_snapshot, snapshot_for_hermes
from skills.browser_awareness.schemas import (
    ActionOutcome,
    ElementInfo,
    InspectionResult,
    PageSnapshot,
    RecommendedAction,
    validate_inspection,
)

# ---------------------------------------------------------------------------
# Selenium + BeautifulSoup stack (v1.1 — Selenium primary, PW fallback)
# ---------------------------------------------------------------------------


class _FakeSeleniumElement:
    def __init__(self, displayed=True, selected=False, tag="button"):
        self.displayed = displayed
        self.selected = selected
        self.tag_used = tag
        self.clicks = 0
        self.typed: list[str] = []
        self.cleared = 0
        self.relative_queries: list[tuple] = []

    def click(self):
        self.clicks += 1

    def clear(self):
        self.cleared += 1

    def send_keys(self, text):
        self.typed.append(text)

    def is_displayed(self):
        return self.displayed

    def is_selected(self):
        return self.selected

    def find_elements(self, by, value):
        self.relative_queries.append((by, value))
        return []


class _FakeSeleniumDriver:
    """Minimal webdriver.Chrome stand-in for the adapter + driver tests."""

    def __init__(self):
        self.located: dict[tuple, list] = {}
        self.scripts: list[tuple] = []
        self.loaded: list[str] = []
        self.url = "https://example.com/"
        self.source = "<html><body>hi</body></html>"
        self.options = None
        self.quit_calls = 0
        self.closed_handles: list[str] = []
        self.switched: list[str] = []
        self.windows = ["tab-chat"]
        self.current = "tab-chat"
        self.switch_to = self

    # -- navigation / pages --------------------------------------------

    def get(self, url):
        self.loaded.append(url)
        self.url = url

    @property
    def page_source(self):
        return self.source

    @property
    def current_url(self):
        return self.url

    @property
    def title(self):
        return "Example"

    def find_element(self, by, value):
        matches = self.located.get((by, value)) or []
        if not matches:
            raise LookupError(f"no element for {(by, value)}")
        return matches[0]

    def find_elements(self, by, value):
        return list(self.located.get((by, value), []))

    def execute_script(self, script, *args):
        self.scripts.append((script, args))
        return "ran"

    # -- tabs (switch_to is self: switch_to.window / .new_window) -------

    @property
    def current_window_handle(self):
        return self.current

    @property
    def window_handles(self):
        return list(self.windows)

    def window(self, handle):
        self.switched.append(handle)
        self.current = handle

    def new_window(self, kind):
        self.windows.append("tab-new")
        self.current = "tab-new"

    def close(self):
        self.closed_handles.append(self.current)

    def quit(self):
        self.quit_calls += 1


def _install_fake_selenium(monkeypatch, chrome_factory=None):
    """Put a minimal selenium package into sys.modules for the test."""
    import sys
    import types

    selenium_mod = types.ModuleType("selenium")
    webdriver_mod = types.ModuleType("selenium.webdriver")
    common_mod = types.ModuleType("selenium.webdriver.common")
    by_mod = types.ModuleType("selenium.webdriver.common.by")
    support_mod = types.ModuleType("selenium.webdriver.support")
    ui_mod = types.ModuleType("selenium.webdriver.support.ui")

    class _FakeBy:
        CSS_SELECTOR = "css selector"
        XPATH = "xpath"
        TAG_NAME = "tag name"

    class _FakeChromeOptions:
        def __init__(self):
            self.arguments: list[str] = []
            self.experimental: dict = {}

        def add_argument(self, argument):
            self.arguments.append(argument)

        def add_experimental_option(self, name, value):
            self.experimental[name] = value

    class _FakeSelect:
        def __init__(self, element):
            self.element = element
            self.by_value: list[str] = []
            self.by_text: list[str] = []
            _install_fake_select_instances.append(self)

        def select_by_value(self, value):
            if value not in getattr(self.element, "select_values", [value]):
                raise ValueError(f"no option {value!r}")
            self.by_value.append(value)

        def select_by_visible_text(self, value):
            self.by_text.append(value)

    webdriver_mod.ChromeOptions = _FakeChromeOptions
    webdriver_mod.Chrome = lambda options=None: chrome_factory(options)
    by_mod.By = _FakeBy
    common_mod.by = by_mod
    webdriver_mod.common = common_mod
    ui_mod.Select = _FakeSelect
    support_mod.ui = ui_mod
    webdriver_mod.support = support_mod
    selenium_mod.webdriver = webdriver_mod
    for name, module in {
        "selenium": selenium_mod,
        "selenium.webdriver": webdriver_mod,
        "selenium.webdriver.common": common_mod,
        "selenium.webdriver.common.by": by_mod,
        "selenium.webdriver.support": support_mod,
        "selenium.webdriver.support.ui": ui_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return _FakeSelect


class TestSeleniumPageAdapter:
    CSS = "css selector"
    XPATH = "xpath"

    def _page(self, monkeypatch, driver=None):
        from skills.browser_awareness.selenium_page import SeleniumPageAdapter

        driver = driver or _FakeSeleniumDriver()
        _install_fake_selenium(monkeypatch)
        return SeleniumPageAdapter(driver), driver

    def test_goto_uses_driver_get(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        page.goto("https://example.com/x", timeout=1000, wait_until="domcontentloaded")
        assert driver.loaded == ["https://example.com/x"]

    def test_locator_click_resolves_css(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        element = _FakeSeleniumElement()
        driver.located[(self.CSS, "#buy")] = [element]
        page.locator("#buy").first.click(timeout=500)
        assert element.clicks == 1

    def test_fill_clears_then_types(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        element = _FakeSeleniumElement()
        driver.located[(self.CSS, "#email")] = [element]
        page.locator("#email").first.fill("hi@example.com", timeout=500)
        assert element.cleared == 1
        assert element.typed == ["hi@example.com"]

    def test_select_option_value_then_text_fallback(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        element = _FakeSeleniumElement()
        element.select_values = ["basic", "pro"]
        driver.located[(self.CSS, "#plan")] = [element]
        locator = page.locator("#plan").first
        locator.select_option("basic", timeout=500)
        locator.select_option("Basic")  # not a value -> visible-text fallback
        # One Select wrapper per select_option call, in order.
        assert _install_fake_select_instances[0].by_value == ["basic"]
        assert _install_fake_select_instances[1].by_text == ["Basic"]

    def test_check_and_uncheck_toggle_by_state(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        unchecked = _FakeSeleniumElement(selected=False)
        checked = _FakeSeleniumElement(selected=True)
        driver.located[(self.CSS, "#a")] = [unchecked]
        driver.located[(self.CSS, "#b")] = [checked]
        page.locator("#a").first.check(timeout=500)
        page.locator("#b").first.uncheck(timeout=500)
        assert unchecked.clicks == 1
        assert checked.clicks == 1

    def test_is_visible_false_when_missing_or_hidden(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        hidden = _FakeSeleniumElement(displayed=False)
        driver.located[(self.CSS, "#ghost")] = [hidden]
        assert page.locator("#ghost").first.is_visible(timeout=100) is False
        assert page.locator("#missing").first.is_visible(timeout=100) is False

    def test_count_is_zero_when_missing(self, monkeypatch):
        page, _ = self._page(monkeypatch)
        assert page.locator("#missing").first.count() == 0

    def test_evaluate_wraps_playwright_arrow(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        element = _FakeSeleniumElement()
        driver.located[(self.CSS, "#a")] = [element]
        page.locator("#a").first.evaluate(
            "(el) => el.disabled || el.getAttribute('aria-disabled') === 'true'"
        )
        script, args = driver.scripts[-1]
        assert script.startswith("return ((el)")
        assert args[0] is element

    def test_element_relative_xpath_locator(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        element = _FakeSeleniumElement()
        driver.located[(self.CSS, "#submit")] = [element]
        form_locator = page.locator("#submit").first.locator("xpath=ancestor::form[1]")
        assert form_locator.count() == 0
        assert element.relative_queries == [(self.XPATH, "ancestor::form[1]")]

    def test_inner_text_and_passthrough(self, monkeypatch):
        page, driver = self._page(monkeypatch)
        body = _FakeSeleniumElement()
        body.text = "Hello world"
        driver.located[(self.CSS, "body")] = [body]
        assert page.inner_text("body") == "Hello world"
        assert page.current_url == "https://example.com/"  # passthrough
        assert page.title == "Example"


class _FakeHtmlPage:
    """A Playwright-shaped page carrying static HTML for the bs4 inspector."""

    def __init__(self, html, body_text="Hello world"):
        self.page_source = html
        self.current_url = "https://example.com/pricing"
        self._body_text = body_text

    def title(self):
        return "Example — Pricing"

    def inner_text(self, selector):
        return self._body_text

    def wait_for_load_state(self, *args, **kwargs):
        pass


class TestBeautifulSoupInspector:
    HTML = """<html><head><title>Example</title></head><body>
        <nav aria-label="Main"><a href="/home">Home</a></nav>
        <button id="buy-now">Buy now</button>
        <button disabled>Locked</button>
        <a href="/ghost" style="display:none">Ghost</a>
        <input type="text" placeholder="Your email" name="email">
        <div role="button" data-testid="save-all">Save all</div>
        <label for="plan">Choose plan</label>
        <select id="plan" name="plan"><option>Basic</option></select>
    </body></html>"""

    def _inspect(self, html):
        pytest.importorskip("bs4")
        from skills.browser_awareness.inspector import BeautifulSoupInspector

        return BeautifulSoupInspector(_FakeHtmlPage(html)).inspect()

    def test_snapshot_identity(self):
        snapshot = self._inspect(self.HTML)
        assert snapshot.url == "https://example.com/pricing"
        assert snapshot.title == "Example — Pricing"
        assert "Hello world" in snapshot.text

    def test_element_kinds_labels_and_selectors(self):
        snapshot = self._inspect(self.HTML)
        by_selector = {e.selector: e for e in snapshot.elements}
        # Unique id wins for the button.
        buy = by_selector["#buy-now"]
        assert (buy.kind, buy.text) == ("button", "Buy now")
        # Unique data-testid for the role=button div.
        save = by_selector['[data-testid="save-all"]']
        assert save.kind == "button" and save.text == "Save all"
        # name-based selector for the input + placeholder carried through.
        email = by_selector['input[name="email"]']
        assert email.kind == "input" and email.placeholder == "Your email"
        # The select is labelled by <label for=plan>.
        plan = by_selector["#plan"]
        assert plan.kind == "select" and plan.label == "Choose plan"
        # nav + inner link are both collected.
        assert any(e.kind == "nav" and e.label == "Main" for e in snapshot.elements)
        assert any(e.kind == "link" and e.href == "/home" for e in snapshot.elements)

    def test_disabled_and_hidden_markup_is_dropped(self):
        snapshot = self._inspect(self.HTML)
        texts = [e.text for e in snapshot.elements]
        assert "Locked" not in texts  # disabled attribute
        assert "Ghost" not in texts  # inline display:none

    def test_page_text_falls_back_to_parsed_body(self):
        pytest.importorskip("bs4")
        from skills.browser_awareness.inspector import _page_text

        page = _FakeHtmlPage("<html><body><p>Parsed text</p></body></html>")
        page.inner_text = lambda selector: ""  # no rendered text available
        assert "Parsed text" in _page_text(page)


def _capture_options(driver):
    """chrome_factory that records the options Chrome was started with."""

    def factory(options):
        driver.options = options
        return driver

    return factory


class TestSeleniumDriverSessions:
    def test_backend_selection(self, monkeypatch):
        from skills.browser_awareness import driver as driver_mod

        monkeypatch.delenv(driver_mod.DRIVER_ENV, raising=False)
        _install_fake_selenium(monkeypatch)  # selenium importable -> primary
        assert driver_mod.driver_backend() == "selenium"
        monkeypatch.setitem(__import__("sys").modules, "selenium", None)  # blocked
        assert driver_mod.driver_backend() == "playwright"
        monkeypatch.setenv(driver_mod.DRIVER_ENV, "playwright")
        assert driver_mod.driver_backend() == "playwright"
        monkeypatch.setenv(driver_mod.DRIVER_ENV, "selenium")
        assert driver_mod.driver_backend() == "selenium"

    def _attach_session(self, monkeypatch):
        from skills.browser_awareness import driver as driver_mod

        driver = _FakeSeleniumDriver()
        _install_fake_selenium(monkeypatch, chrome_factory=_capture_options(driver))
        monkeypatch.setenv("BROWSER_AWARENESS_CDP_URL", "http://127.0.0.1:9222")
        session = driver_mod.open_session("https://example.com/x")
        return session, driver

    def test_attach_opens_tab_via_debugger_address(self, monkeypatch):
        from skills.browser_awareness.inspector import BeautifulSoupInspector
        from skills.browser_awareness.selenium_page import SeleniumPageAdapter

        session, driver = self._attach_session(monkeypatch)
        assert driver.options.experimental == {"debuggerAddress": "127.0.0.1:9222"}
        assert driver.loaded == ["https://example.com/x"]
        assert driver.current == "tab-new"  # a NEW TAB, not a new browser
        assert isinstance(session.page, SeleniumPageAdapter)
        assert session.inspector_factory is BeautifulSoupInspector
        session.close()
        # Only our tab closed; focus restored; the browser was NOT quit.
        assert driver.closed_handles == ["tab-new"]
        assert driver.current == "tab-chat"
        assert driver.quit_calls == 0
        assert session.page is None

    def test_launch_mode_owns_browser_and_quits(self, monkeypatch, tmp_path):
        from skills.browser_awareness import driver as driver_mod

        # Env override keeps the profile registry (and the real sarthi.db)
        # out of this test entirely.
        monkeypatch.setenv(driver_mod.PROFILE_DIR_ENV, str(tmp_path / "profile"))
        driver = _FakeSeleniumDriver()
        _install_fake_selenium(monkeypatch, chrome_factory=_capture_options(driver))
        monkeypatch.delenv("BROWSER_AWARENESS_CDP_URL", raising=False)
        monkeypatch.delenv("BROWSER_AWARENESS_HEADLESS", raising=False)
        session = driver_mod.open_session("https://example.com/x")
        user_data_args = [a for a in driver.options.arguments if a.startswith("--user-data-dir=")]
        assert len(user_data_args) == 1  # exactly one profile dir
        assert user_data_args[0] == f"--user-data-dir={tmp_path / 'profile'}"
        assert session.inspector_factory is not None
        session.close()
        assert driver.quit_calls == 1  # we own this browser — quit it
        assert session.page is None

    def test_playwright_dispatch_when_pinned(self, monkeypatch):
        from skills.browser_awareness import driver as driver_mod

        calls = []
        monkeypatch.setenv(driver_mod.DRIVER_ENV, "playwright")
        monkeypatch.setattr(
            driver_mod, "_attach_session", lambda cdp, url: calls.append((cdp, url))
        )
        monkeypatch.setenv("BROWSER_AWARENESS_CDP_URL", "http://127.0.0.1:9222")
        driver_mod.open_session("https://example.com/x")
        assert calls == [("http://127.0.0.1:9222", "https://example.com/x")]


class TestLaunchProfileResolution:
    """Launch-mode profile selection: DB-registered persistent profile,
    env override, and the temporary fallback when nothing is registered.
    All DB access is pointed at a temp SQLite file — never the real sarthi.db.
    """

    @pytest.fixture(autouse=True)
    def _isolated_profile_db(self, monkeypatch, tmp_path):
        """database.profiles.get_database -> a temp-file DatabaseManager."""
        from database.manager import DatabaseManager
        from skills.browser_awareness import driver as driver_mod

        db = DatabaseManager(tmp_path / "profiles.db")
        monkeypatch.setattr("database.profiles.get_database", lambda: db)
        monkeypatch.delenv(driver_mod.PROFILE_DIR_ENV, raising=False)
        self.db = db
        self.tmp_path = tmp_path

    def _launch(self, monkeypatch):
        from skills.browser_awareness import driver as driver_mod

        driver = _FakeSeleniumDriver()
        _install_fake_selenium(monkeypatch, chrome_factory=_capture_options(driver))
        monkeypatch.delenv("BROWSER_AWARENESS_CDP_URL", raising=False)
        session = driver_mod.open_session("https://example.com/x")
        return session, driver

    @staticmethod
    def _user_data_dir(options):
        args = [a for a in options.arguments if a.startswith("--user-data-dir=")]
        assert len(args) == 1
        return args[0].removeprefix("--user-data-dir=")

    def test_registered_profile_is_reused(self, monkeypatch):
        from database.profiles import ensure_default_profile

        profile_dir = ensure_default_profile(self.db, profile_dir=self.tmp_path / "prof")
        session, driver = self._launch(monkeypatch)
        assert self._user_data_dir(driver.options) == str(profile_dir)
        assert session._temp_owner is None  # persistent — nothing to clean up
        session.close()
        assert driver.quit_calls == 1  # we still own this browser

    def test_first_run_registers_default_profile(self, monkeypatch):

        session, driver = self._launch(monkeypatch)
        user_data = self._user_data_dir(driver.options)
        # The first launch registered the persistent profile and used it.
        assert session._temp_owner is None
        assert Path(user_data).name == ".chrome-profile"
        row = self.db.fetch_one("SELECT value FROM browser_profiles WHERE name = 'default'")
        assert row["value"] == user_data
        session.close()
        assert driver.quit_calls == 1

    def test_env_override_wins_over_db(self, monkeypatch):
        from database.profiles import PROFILE_DIR_ENV, ensure_default_profile

        ensure_default_profile(self.db, profile_dir=self.tmp_path / "prof")
        override = self.tmp_path / "custom-profile"
        monkeypatch.setenv(PROFILE_DIR_ENV, str(override))
        session, driver = self._launch(monkeypatch)
        assert self._user_data_dir(driver.options) == str(override)
        assert session._temp_owner is None
        session.close()

    def test_resolve_prefers_env_then_db_then_registers(self, monkeypatch):
        from database.profiles import PROFILE_DIR_ENV, set_profile_dir
        from skills.browser_awareness import driver as driver_mod

        # Nothing registered yet -> first-use registration kicks in.
        registered = driver_mod._resolve_profile_dir()
        assert Path(registered).name == ".chrome-profile"
        assert driver_mod._resolve_profile_dir() == registered  # stable

        # A moved entry (set_profile_dir) is what future launches use.
        moved = set_profile_dir(self.tmp_path / "new-home", db=self.db)
        assert driver_mod._resolve_profile_dir() == str(moved)

        # And the env override wins over everything.
        monkeypatch.setenv(PROFILE_DIR_ENV, str(self.tmp_path / "override"))
        assert driver_mod._resolve_profile_dir() == str(self.tmp_path / "override")

    def test_db_failure_falls_back_to_temp(self, monkeypatch):
        from skills.browser_awareness import driver as driver_mod

        def _boom():
            raise RuntimeError("db unavailable")

        monkeypatch.setattr("database.profiles.get_database", _boom)
        assert driver_mod._resolve_profile_dir() is None


class TestManagerInspectorPairing:
    def test_session_inspector_factory_wins_when_none_injected(self):
        from skills.browser_awareness.driver import BrowserSession
        from skills.browser_awareness.manager import BrowserAwarenessManager

        used = []

        class _RecordingInspector:
            def __init__(self, page):
                used.append(page)

            def inspect(self):
                return build_page_snapshot(
                    url="https://example.com", title="T", page_text="hi", raw_elements=[]
                )

        class _Hermes:
            def observe(self, objective, snapshot):
                return InspectionResult(status="done", understanding="all good")

        class _Executor:
            def __init__(self, page):
                pass

            def perform(self, inspection, snapshot, confirmed=False):
                return ActionOutcome(ok=True, status="executed", message="ok")

        class _Page:
            def close(self):
                pass

        session = BrowserSession(page=_Page(), inspector_factory=_RecordingInspector)
        page = session.page  # run() closes the session -> page becomes None
        manager = BrowserAwarenessManager(
            session_factory=lambda url: session,
            hermes=_Hermes(),
            executor_factory=_Executor,
            announce_progress=False,
        )
        result = manager.run(url="https://example.com", objective="describe the page")
        assert result.status == "completed"
        assert used == [page]  # the session's backend pairing was used


# Populated by _install_fake_selenium so tests can inspect Select calls.
_install_fake_select_instances: list = []


def _element(
    kind="button",
    text="Pricing",
    selector="a:nth-of-type(2)",
    visible=True,
    enabled=True,
    name="",
    placeholder="",
    label="",
    href="",
):
    return ElementInfo(
        id="el_1",
        kind=kind,
        text=text,
        selector=selector,
        visible=visible,
        enabled=enabled,
        name=name,
        placeholder=placeholder,
        label=label,
        href=href,
    )


def _snapshot(elements=None, text="Page body text.", url="https://example.com/"):
    return PageSnapshot(
        url=url,
        title="Example",
        text=text,
        elements=elements or [_element()],
    )


class TestSnapshotBuilding:
    def test_hidden_and_disabled_elements_are_dropped(self):
        raw = [
            {"kind": "button", "text": "ok", "selector": "#a", "visible": True, "enabled": True},
            {
                "kind": "button",
                "text": "ghost",
                "selector": "#b",
                "visible": False,
                "enabled": True,
            },
            {
                "kind": "button",
                "text": "locked",
                "selector": "#c",
                "visible": True,
                "enabled": False,
            },
            {"kind": "link", "text": "no selector", "visible": True, "enabled": True},
        ]
        snapshot = build_page_snapshot("https://x.io", "X", "body", raw)
        assert [e.text for e in snapshot.elements] == ["ok"]

    def test_element_cap_is_enforced(self):
        raw = [
            {
                "kind": "link",
                "text": f"l{i}",
                "selector": f"#id{i}",
                "visible": True,
                "enabled": True,
            }
            for i in range(60)
        ]
        snapshot = build_page_snapshot("https://x.io", "X", "body", raw, max_elements=10)
        assert len(snapshot.elements) == 10
        assert snapshot.elements_truncated is True

    def test_text_is_capped_and_flag_set(self):
        snapshot = build_page_snapshot("https://x.io", "X", "word " * 1000, [], max_text_chars=100)
        assert snapshot.text_truncated is True
        assert len(snapshot.text) < 200

    def test_sensitive_field_values_never_leak(self):
        raw = [
            {
                "kind": "input",
                "name": "password",
                "placeholder": "SuperSecret123",
                "selector": "input[name='password']",
                "visible": True,
                "enabled": True,
            }
        ]
        snapshot = build_page_snapshot("https://x.io", "X", "", raw)
        element = snapshot.elements[0]
        assert "SuperSecret123" not in element.placeholder

    def test_duplicate_selectors_are_dropped(self):
        raw = [
            {
                "kind": "button",
                "text": "first",
                "selector": "#dup",
                "visible": True,
                "enabled": True,
            },
            {
                "kind": "button",
                "text": "second",
                "selector": "#dup",
                "visible": True,
                "enabled": True,
            },
        ]
        snapshot = build_page_snapshot("https://x.io", "X", "", raw)
        assert len(snapshot.elements) == 1

    def test_hermes_block_lists_element_ids_and_kinds(self):
        snapshot = build_page_snapshot(
            "https://example.com",
            "Example",
            "Welcome",
            [
                {
                    "kind": "link",
                    "text": "Pricing",
                    "href": "/pricing",
                    "selector": "#pricing",
                    "visible": True,
                    "enabled": True,
                }
            ],
        )
        block = snapshot_for_hermes(snapshot)
        assert "[link]" in block and "id=el_1" in block and "Pricing" in block
        assert "<html" not in block  # never raw HTML


class _FakeProvider:
    """Provider stand-in returning canned text (or raising)."""

    def __init__(self, text="", error=""):
        self._text = text
        self._error = error

    def generate(self, task):
        from hermes.providers.base import ProviderResponse

        if self._error:
            return ProviderResponse(
                success=False, provider="Ollama", model="hermes3:8b", text="", error=self._error
            )
        return ProviderResponse(
            success=True, provider="Ollama", model="hermes3:8b", text=self._text
        )


class TestHermesInspector:
    def _inspector(self, provider):
        from skills.browser_awareness.hermes_inspector import HermesInspector

        return HermesInspector(provider=provider)

    def test_valid_observation_parsed(self):
        payload = (
            '{"status": "continue", "understanding": "Pricing link visible.", '
            '"action": {"type": "click", "element_id": "el_1", '
            '"rationale": "opens pricing"}}'
        )
        provider = _FakeProvider(text=payload)
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "continue"
        assert result.action is not None
        assert result.action.type == "click"
        assert result.action.element_id == "el_1"

    def test_json_in_fences_parsed(self):
        provider = _FakeProvider(
            text='```json\n{"status": "done", "understanding": "on pricing"}\n```'
        )
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "done"
        assert result.action is None

    def test_garbage_is_blocked_not_executed(self):
        provider = _FakeProvider(text="sure, I'll click the pricing link for you!")
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "blocked"

    def test_provider_failure_is_blocked(self):
        provider = _FakeProvider(error="model down")
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "blocked"

    def test_provider_exception_is_blocked(self):
        class ExplodingProvider:
            def generate(self, task):
                raise RuntimeError("boom")

        result = self._inspector(ExplodingProvider()).observe("find pricing", _snapshot())
        assert result.status == "blocked"

    def test_malformed_schema_is_blocked(self):
        provider = _FakeProvider(
            text='{"status": "continue", "action": {"type": "hack", "element_id": "el_1"}}'
        )
        result = self._inspector(provider).observe("find pricing", _snapshot())
        assert result.status == "blocked"


class TestSafetyGate:
    def test_valid_click_passes(self):
        inspection = InspectionResult(
            status="continue",
            action=RecommendedAction(type="click", element_id="el_1"),
        )
        assert validate_inspection(inspection, _snapshot()) == []

    def test_unknown_element_rejected(self):
        inspection = InspectionResult(
            status="continue",
            action=RecommendedAction(type="click", element_id="el_99"),
        )
        assert validate_inspection(inspection, _snapshot())

    def test_kind_mismatch_rejected(self):
        """Hermes may not type into a link."""
        inspection = InspectionResult(
            status="continue",
            action=RecommendedAction(type="type", element_id="el_1", value="hi"),
        )
        snapshot = _snapshot(elements=[_element(kind="link")])
        problems = validate_inspection(inspection, snapshot)
        assert any("link" in p for p in problems)

    def test_hidden_element_rejected(self):
        inspection = InspectionResult(
            status="continue",
            action=RecommendedAction(type="click", element_id="el_1"),
        )
        snapshot = _snapshot(elements=[_element(visible=False)])
        assert any("hidden" in p for p in validate_inspection(inspection, snapshot))

    def test_navigate_requires_http(self):
        bad = InspectionResult(
            status="continue", action=RecommendedAction(type="navigate", url="file:///etc/passwd")
        )
        assert validate_inspection(bad, _snapshot())
        good = InspectionResult(
            status="continue",
            action=RecommendedAction(type="navigate", url="https://example.com/pricing"),
        )
        assert validate_inspection(good, _snapshot()) == []

    def test_done_needs_no_action(self):
        inspection = InspectionResult(status="done", understanding="reached")
        assert validate_inspection(inspection, _snapshot()) == []


class TestSelectorSafety:
    def _is_safe(self, selector):
        from skills.browser_awareness.executor import _is_safe_selector

        return _is_safe_selector(selector)

    @pytest.mark.parametrize(
        "selector",
        [
            "#pricing",
            '[data-testid="pricing"]',
            'input[name="email"]',
            "button:nth-of-type(2)",
            "div:nth-of-type(1) > a:nth-of-type(3)",
            "a",
        ],
    )
    def test_generated_selectors_allowed(self, selector):
        assert self._is_safe(selector)

    @pytest.mark.parametrize(
        "selector",
        [
            "javascript:alert(1)",
            "#pricing img[src=x onerror=alert(1)]",
            "a[href='/x']",
            "button > script",
            'body:has-text("drop")',
            ".classy",
            "xpath=//a",
        ],
    )
    def test_foreign_selectors_denied(self, selector):
        assert not self._is_safe(selector)


class _FakeSession:
    def __init__(self):
        self.page = object()
        self.closed = False

    def close(self):
        self.closed = True


class _ScriptedHermes:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def observe(self, objective, snapshot):
        self.calls.append((objective, snapshot.url))
        return self._results.pop(0)


class _RecordingExecutor:
    """Records perform() calls; the outcome script decides the manager path."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    def perform(self, inspection, snapshot, confirmed=False):
        return self._outcomes.pop(0)


def _click_action(element_id="el_1"):
    return InspectionResult(
        status="continue",
        understanding="clicking",
        action=RecommendedAction(type="click", element_id=element_id, rationale="next"),
    )


class TestManagerLoop:
    def _manager(self, session, snapshot, hermes, outcomes, announce=False):
        from skills.browser_awareness.manager import BrowserAwarenessManager

        class FixedInspector:
            def __init__(self, page):
                self.page = page
                self.count = 0

            def inspect(self):
                self.count += 1
                return snapshot

        def executor_factory(page):
            return _RecordingExecutor(outcomes)

        return BrowserAwarenessManager(
            session_factory=lambda url: session,
            inspector_factory=FixedInspector,
            hermes=hermes,
            executor_factory=executor_factory,
            announce_progress=announce,
        )

    def test_completes_after_execute_then_done(self):
        session = _FakeSession()
        snapshot = _snapshot()
        hermes = _ScriptedHermes(
            [_click_action(), InspectionResult(status="done", understanding="Found it.")]
        )
        manager = self._manager(
            session,
            snapshot,
            hermes,
            [ActionOutcome(ok=True, status="executed", message="Clicked el_1.")],
        )

        result = manager.run("https://example.com", "find pricing")
        assert result.status == "completed"
        assert result.success is True
        assert result.final_understanding == "Found it."
        assert session.closed is True  # temporary context destroyed
        assert len(hermes.calls) == 2
        assert "Clicked el_1" in " ".join(result.steps)

    def test_blocked_observation_stops_immediately(self):
        session = _FakeSession()
        hermes = _ScriptedHermes([InspectionResult(status="blocked", message="login required")])
        manager = self._manager(session, _snapshot(), hermes, [])

        result = manager.run("https://example.com", "buy thing")
        assert result.status == "blocked"
        assert "login" in result.message
        assert session.closed is True

    def test_high_impact_action_halts_for_confirmation(self):
        session = _FakeSession()
        inspection = _click_action()
        inspection.action.requires_confirmation = True
        hermes = _ScriptedHermes([inspection])
        manager = self._manager(
            session,
            _snapshot(),
            hermes,
            [ActionOutcome(ok=False, status="needs_confirmation", message="confirm?")],
        )

        result = manager.run("https://example.com", "purchase", confirm=False)
        assert result.status == "needs_confirmation"
        assert session.closed is True

    def test_session_closed_even_when_run_raises(self):
        session = _FakeSession()

        class BrokenInspector:
            def inspect(self):
                raise RuntimeError("boom")

        from skills.browser_awareness.manager import BrowserAwarenessManager

        manager = BrowserAwarenessManager(
            session_factory=lambda url: session,
            inspector_factory=lambda page: BrokenInspector(),
            hermes=_ScriptedHermes([]),
            executor_factory=lambda page: _RecordingExecutor([]),
            announce_progress=False,
        )
        result = manager.run("https://example.com")
        assert result.status == "failed"
        assert session.closed is True

    def test_step_limit_stops_cleanly(self):
        session = _FakeSession()
        hermes = _ScriptedHermes([_click_action()] * 20)
        manager = self._manager(
            session,
            _snapshot(),
            hermes,
            [ActionOutcome(ok=True, status="executed", message="ok")] * 20,
        )
        result = manager.run("https://example.com", "task", max_steps=3)
        assert result.status == "blocked"
        assert "3 steps" in result.message
        assert session.closed is True

    def test_voice_progress_announces_start_action_and_done(self, monkeypatch):
        """Live spoken progress mirrors the AI-chain announcement pattern."""
        spoken = []
        monkeypatch.setattr("skills.browser_awareness.manager.announce", spoken.append)
        session = _FakeSession()
        snapshot = _snapshot(elements=[_element(kind="link", text="Pricing")])
        hermes = _ScriptedHermes(
            [_click_action(), InspectionResult(status="done", understanding="Found it.")]
        )
        manager = self._manager(
            session,
            snapshot,
            hermes,
            [ActionOutcome(ok=True, status="executed", message="Clicked el_1.")],
            announce=True,
        )

        result = manager.run("https://example.com", "find pricing")
        assert result.status == "completed"
        # Start: names the site, like "Hands off..." does for the AI chain.
        assert spoken[0].startswith("Browser awareness started.")
        assert "example.com" in spoken[0]
        # Mid-run: what is happening, in user language (not element ids).
        assert "Clicking Pricing" in spoken[1]
        # Terminal: outcome summary.
        assert spoken[2].startswith("Done.")


class TestBrowseRequestParsing:
    def _parse(self, text):
        from skills.browser_awareness.main import parse_browse_request

        return parse_browse_request(text)

    def test_slash_command(self):
        url, objective = self._parse("/browse example.com and find the pricing page")
        assert url == "https://example.com"
        assert "pricing" in objective

    def test_open_sentence(self):
        url, objective = self._parse("open example.com and find the More Information link")
        assert url == "https://example.com"
        assert "More Information" in objective

    def test_full_url_with_path_kept(self):
        url, _ = self._parse("browse https://example.com/pricing tell me about plans")
        assert url == "https://example.com/pricing"

    def test_no_objective_describes_page(self):
        url, objective = self._parse("/browse example.com")
        assert url == "https://example.com"
        assert objective == ""

    def test_no_url_returns_empty(self):
        assert self._parse("what is the weather") == ("", "")


class TestSkill:
    def _skill(self):
        from skills.browser_awareness.main import BrowserAwarenessSkill

        return BrowserAwarenessSkill()

    def test_test_mode_plans_without_browser(self, monkeypatch):
        import brain.modes as modes

        monkeypatch.setattr(modes, "_test_mode", True)
        result = self._skill().execute(
            Intent(action="browse", raw_text="/browse example.com and find the pricing page")
        )
        assert result["success"] is True
        assert result["status"] == "planned"
        assert "example.com" in result["result"]["message"]

    def test_unknown_action_not_claimed(self):
        result = self._skill().execute(Intent(action="play", target="music"))
        assert result["success"] is False
        assert "handled" not in result  # executor keeps searching

    def test_missing_url_errors_clearly(self):
        result = self._skill().execute(Intent(action="browse", raw_text="browse"))
        assert result["success"] is False
        assert "website" in result["error"]


class TestInterpreterRouting:
    def test_open_domain_and_task_becomes_single_browse_intent(self):
        intent = interpret("open example.com and find the pricing page")
        assert intent.action == "browse"
        assert intent.target == "example.com"
        assert intent.raw_text  # skill re-parses url + objective from raw text

    def test_known_youtube_stays_two_fast_intents(self):
        intents = interpret_many("open youtube and play motivation video")
        assert [i.action for i in intents] == ["open", "play"]

    def test_known_domain_youtube_com_stays_fast(self):
        intents = interpret_many("open youtube.com and play a song")
        assert [i.action for i in intents] == ["open", "play"]

    def test_browse_action_word(self):
        intent = interpret("browse example.com")
        assert intent.action == "browse"


class TestBrainBrowseHandler:
    def test_browse_intent_delegates_to_awareness_skill(self, monkeypatch):
        calls = {}

        class FakeAwarenessSkill:
            @staticmethod
            def execute(intent):
                calls["action"] = intent.action
                return {
                    "success": True,
                    "handled": True,
                    "status": "completed",
                    "result": {"message": "Found the pricing page."},
                }

        monkeypatch.setattr(
            "skills.browser_awareness.main.BrowserAwarenessSkill", FakeAwarenessSkill
        )
        from brain.executor import BrainExecutor

        executor = BrainExecutor()
        result = executor.execute(
            Intent(
                action="browse",
                target="example.com",
                raw_text="open example.com and find the pricing page",
            )
        )
        assert result["success"] is True
        assert result["status"] == "completed"
        assert calls["action"] == "browse"
