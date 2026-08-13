from fastapi import APIRouter

from skills.browser.models import BrowserAction, BrowserPage, BrowserSelection
from skills.browser.service import browser_service

router = APIRouter(prefix="/browser", tags=["Browser"])


@router.post("/page")
def receive_page(page: BrowserPage):
    return browser_service.receive_page(page)


@router.post("/selection")
def receive_selection(selection: BrowserSelection):
    return browser_service.receive_selection(selection)


@router.get("/current")
def current_page():
    return browser_service.get_current_page()


@router.get("/session")
def current_session():
    return browser_service.get_session()


@router.post("/action")
def execute_action(action: BrowserAction):
    return browser_service.execute_action(action)
