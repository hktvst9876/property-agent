"""
integrations/whatsapp.py — the WhatsApp Web channel (send + receive).

This is how the agent actually texts people, with NO paid API: it drives
web.whatsapp.com in a real browser using a PERSISTENT profile, so you scan the
QR code once with your phone and stay logged in across runs.

  ⚠️  This automates the WhatsApp WEB client. It is unofficial and against
      WhatsApp's Terms of Service; heavy use can get a number banned. You chose
      this channel knowing that. Keep volume human-paced.

Two clients behind one factory:
  - WhatsAppClient      — live, Selenium-driven. Needs `pip install selenium` and
                          Chrome installed. Used when WHATSAPP_MODE=live.
  - MockWhatsAppClient  — no browser. Outbound goes to an in-memory outbox + the
                          console; inbound can be injected for tests/`simulate`.
                          The default, so everything is runnable offline.

Selenium is imported lazily so the rest of the project never depends on it.
"""

from __future__ import annotations
import os
import time
from pathlib import Path
from urllib.parse import quote

# WhatsApp Web DOM selectors change over time. Keep them here so there's one place
# to update when a send/receive stops working.
_SEL_SEARCH_BOX = '//div[@contenteditable="true"][@data-tab="3"]'
_SEL_MSG_BOX = '//div[@contenteditable="true"][@data-tab="10"]'
_SEL_UNREAD = '//span[contains(@aria-label,"unread")]'

_PROFILE_DIR = os.environ.get(
    "WHATSAPP_PROFILE_DIR",
    str(Path(__file__).resolve().parent.parent / ".wa_profile"),
)


# -------------------------------------------------------------------------
# Mock client — the default. Lets the whole inbound/outbound loop run offline.
# -------------------------------------------------------------------------
class MockWhatsAppClient:
    def __init__(self) -> None:
        self.outbox: list[dict] = []
        self._inbound: list[dict] = []

    def connect(self) -> None:
        print("  [WA mock] connected (no browser).")

    def send(self, phone: str, text: str) -> dict:
        msg = {"phone": phone, "text": text}
        self.outbox.append(msg)
        print(f"  [WA mock] -> {phone}: {text.splitlines()[0][:70]}...")
        return {"sent": True, "mock": True, **msg}

    def inject(self, phone: str, text: str, has_media: bool = False) -> None:
        """Queue a fake inbound message (tests / simulate)."""
        self._inbound.append({"from_phone": phone, "text": text, "has_media": has_media})

    def fetch_unread(self) -> list[dict]:
        msgs, self._inbound = self._inbound, []
        return msgs

    def close(self) -> None:
        pass


# -------------------------------------------------------------------------
# Live client — Selenium-driven WhatsApp Web.
# -------------------------------------------------------------------------
class WhatsAppClient:
    def __init__(self, profile_dir: str = _PROFILE_DIR) -> None:
        self.profile_dir = profile_dir
        self._driver = None

    def connect(self) -> None:
        """Launch Chrome with the persistent profile and wait until logged in.
        First run shows a QR — scan it with WhatsApp on your phone."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError as exc:
            raise RuntimeError(
                "Live WhatsApp needs Selenium + Chrome. Run: pip install selenium "
                "(and have Chrome installed). Or keep WHATSAPP_MODE=mock."
            ) from exc

        opts = Options()
        opts.add_argument(f"--user-data-dir={self.profile_dir}")
        opts.add_argument("--profile-directory=Default")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        self._driver = webdriver.Chrome(options=opts)  # Selenium Manager fetches the driver
        self._driver.get("https://web.whatsapp.com")

        print("  [WA] If prompted, scan the QR with your phone (one time)...")
        WebDriverWait(self._driver, 120).until(
            EC.presence_of_element_located((By.XPATH, _SEL_SEARCH_BOX))
        )
        print("  [WA] Logged in.")

    def send(self, phone: str, text: str) -> dict:
        """Send a message by opening the chat via the send-URL, then pressing Enter."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        digits = "".join(c for c in phone if c.isdigit())
        self._driver.get(f"https://web.whatsapp.com/send?phone={digits}&text={quote(text)}")
        box = WebDriverWait(self._driver, 30).until(
            EC.presence_of_element_located((By.XPATH, _SEL_MSG_BOX))
        )
        time.sleep(1.5)            # let the prefilled text settle
        box.send_keys(Keys.ENTER)
        time.sleep(1.0)
        return {"sent": True, "phone": digits}

    def fetch_unread(self) -> list[dict]:
        """Best-effort read of unread chats. WhatsApp's DOM is volatile, so this is
        the most fragile part — selectors live at the top of this file. Returns a
        list of {"from_phone", "text"}."""
        from selenium.webdriver.common.by import By

        results: list[dict] = []
        unread = self._driver.find_elements(By.XPATH, _SEL_UNREAD)
        for badge in unread:
            try:
                chat = badge.find_element(By.XPATH, "./ancestor::div[@role='listitem']")
                chat.click()
                time.sleep(1.0)
                bubbles = self._driver.find_elements(
                    By.XPATH, '//div[contains(@class,"message-in")]//span[@dir="ltr"]')
                text = bubbles[-1].text if bubbles else ""
                # Best-effort: an incoming image/document bubble means a photo was sent.
                has_media = bool(self._driver.find_elements(
                    By.XPATH, '//div[contains(@class,"message-in")]//img[@src]'))
                if not text and not has_media:
                    continue
                # The chat header title is the contact name/number.
                header = self._driver.find_element(
                    By.XPATH, '//header//span[@dir="auto"]').text
                results.append({"from_phone": header, "text": text or "[photo]",
                                "has_media": has_media})
            except Exception:
                continue  # one bad chat shouldn't stop the rest
        return results

    def close(self) -> None:
        if self._driver:
            self._driver.quit()
            self._driver = None


# -------------------------------------------------------------------------
# Factory — one shared client per process.
# -------------------------------------------------------------------------
_client = None


def get_client():
    """Return the WhatsApp client for the current mode (live or mock), connected."""
    global _client
    if _client is None:
        mode = os.environ.get("WHATSAPP_MODE", "mock").lower()
        _client = WhatsAppClient() if mode == "live" else MockWhatsAppClient()
        _client.connect()
    return _client
