"""
Save Authentication State
=========================

Run this script once to log in to eBay manually in a visible browser.
After you sign in and solve any CAPTCHA, press Enter in the terminal.
The browser's cookies and localStorage are saved to ``auth_state.json``
so automated tests can reuse them without triggering bot detection.

Usage::

    python save_auth_state.py

The saved state file is gitignored and never committed.
Re-run whenever your session expires or cookies are cleared.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_STATE_FILE = Path(__file__).parent / "auth_state.json"


def main() -> None:
    print("\n=== eBay Auth State Saver ===\n")
    print("A browser window will open. Please:")
    print("  1. Sign in to your eBay account")
    print("  2. Solve any CAPTCHA / verification prompts")
    print("  3. Make sure you see the eBay home page (logged in)")
    print("  4. Come back here and press ENTER to save\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto("https://www.ebay.com")

        input("\n>>> Press ENTER after you've signed in and passed any verification... ")

        context.storage_state(path=str(AUTH_STATE_FILE))
        print(f"\nAuth state saved to: {AUTH_STATE_FILE}")
        print("Automated tests will now use this session.\n")

        browser.close()


if __name__ == "__main__":
    main()
