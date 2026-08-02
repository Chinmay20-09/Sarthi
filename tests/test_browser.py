from skills.browser.models import BrowserPage
from skills.browser.service import browser_service

page = BrowserPage(title="OpenAI", url="https://openai.com", text="Welcome to OpenAI")

browser_service.receive_page(page)
print(browser_service.get_current_page())
