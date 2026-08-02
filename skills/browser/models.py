from typing import Optional, List, Literal
from pydantic import BaseModel,Field

class BrowserPage(BaseModel):
    title: str
    url: str
    text: str
    html: Optional[str] = None


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
        "refresh"
    ]

    selector: Optional[str] = None
    text: Optional[str] = None
    amount: Optional[int] = None
    url: Optional[str] = None
    tab_id: Optional[int] = None


class BrowserSession(BaseModel):
    current_page: Optional[BrowserPage] = None
    selected_text: Optional[BrowserSelection] = None
    tabs: List[BrowserTab] = Field(default_factory=list)