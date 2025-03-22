from playwright.sync_api import sync_playwright, Browser, Page
import base64

class LocalPlaywrightComputer:
    environment = "browser"
    dimensions = (1024, 768)

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._page = self._browser.new_page()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def goto(self, url: str) -> None:
        self._page.goto(url)

    def screenshot(self) -> str:
        png_bytes = self._page.screenshot(full_page=False)
        return base64.b64encode(png_bytes).decode("utf-8")

    def fill(self, selector: str, text: str) -> None:
        self._page.fill(selector, text)

    def press(self, selector: str, key: str) -> None:
        self._page.press(selector, key)

    def click(self, selector: str) -> None:
        self._page.click(selector)

    def wait_for_selector(self, selector: str, timeout: int = 15000) -> None:
        self._page.wait_for_selector(selector, timeout=timeout)

    def get_page(self) -> Page:
        return self._page

    def get_current_url(self) -> str:
        return self._page.url
