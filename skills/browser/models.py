from typing import Literal

from pydantic import BaseModel, Field


class BrowserPage(BaseModel):
    title: str
    url: str
    text: str
    html: str | None = None


class BrowserSelection(BaseModel):
    text: str
    url: str


class BrowserTab(BaseModel):
    id: int
    title: str
    url: str
    active: bool


class BrowserAction(BaseModel):
    action: Literal[
        "scroll",
        "scroll_to",
        "click",
        "type",
        "open_tab",
        "close_tab",
        "focus_tab",
        "back",
        "forward",
        "refresh",
    ]

    selector: str | None = None
    text: str | None = None
    amount: int | None = None
    url: str | None = None
    tab_id: int | None = None


class BrowserSession(BaseModel):
    current_page: BrowserPage | None = None
    selected_text: BrowserSelection | None = None
    tabs: list[BrowserTab] = Field(default_factory=list)
