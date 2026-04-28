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

            time.sleep(2)
            page.screenshot(path="verification/home_page.png", full_page=True)
            print("Screenshot saved to verification/home_page.png")

            # Go to Run Reconciliation (which is active)
            page.locator('label').filter(has_text='Run Reconciliation').click(force=True)
            time.sleep(2) # Wait for page to render

            # Take a screenshot of the Reconciliation page to show the Date inputs
            page.screenshot(path="verification/reconciliation_page.png", full_page=True)
            print("Screenshot saved to verification/reconciliation_page.png")

            # Let's also check Date Range mode
            page.locator('label').filter(has_text='📆 Date Range').click(force=True)
            time.sleep(2)
            page.screenshot(path="verification/reconciliation_page_range.png", full_page=True)
            print("Screenshot saved to verification/reconciliation_page_range.png")

            # Go to Import Data
            page.locator('label').filter(has_text='Import Data').click(force=True)
            time.sleep(2) # Wait for page to render

            page.screenshot(path="verification/import_page.png", full_page=True)
            print("Screenshot saved to verification/import_page.png")

        except Exception as e:
            print(f"Error during verification: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_ui()
