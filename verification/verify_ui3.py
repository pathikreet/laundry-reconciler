import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.sync_api import sync_playwright

def verify_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto("http://localhost:8503")

            # Wait for Streamlit to render
            page.wait_for_selector('div.stApp', timeout=10000)

            # Use get_by_role for tabs
            page.get_by_role('tab', name='✍️ Manual Entry').click()
            time.sleep(2)

            # Scroll down to ensure all fields are visible
            page.mouse.wheel(0, 500)
            time.sleep(1)

            page.screenshot(path="verification/notepad_form_scrolled.png", full_page=True)
            print("Screenshot saved to verification/notepad_form_scrolled.png")

        except Exception as e:
            print(f"Error during verification: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_ui()
