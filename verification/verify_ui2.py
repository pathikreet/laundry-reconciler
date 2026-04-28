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
            page.goto("http://localhost:8501")

            # Wait for Streamlit to render
            page.wait_for_selector('div.stApp', timeout=10000)

            # Go to Import Data
            page.locator('label').filter(has_text='Import Data').click(force=True)
            time.sleep(2) # Wait for page to render

            # It's locked. We need to upload CRM Sales.
            # But the Notepad manual entry is not visible until Step 1 to 4 are done...
            # Actually, we can just use the mock script approach to render the notepad step in isolation!

        except Exception as e:
            print(f"Error during verification: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_ui()
