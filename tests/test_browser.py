from skills.browser.service import browser_service
from skills.browser.models import BrowserPage

page = BrowserPage(
    title="OpenAI",
    url="https://openai.com",
    text="Welcome to OpenAI"
)

browser_service.receive_page(page)
print(browser_service.get_current_page())