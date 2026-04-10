import sys
import os
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            record_video_dir="verification/videos/"
        )
        page = context.new_page()

        print("Navigating to local Streamlit app...")
        page.goto('http://localhost:8501')
        page.wait_for_selector('text="🧺 Laundry Reconciler"', timeout=10000)

        print("Navigating to Import Data page...")
        page.locator('label').filter(has_text='Import Data').click()
        time.sleep(2)

        print("Mocking CRM Sales import to unlock Notepad tab...")
        page.locator('input[type="file"]').first.set_input_files('sample/SalesAndDeliveryCRMExport-November.xlsx')
        time.sleep(2)
        page.locator('button').filter(has_text='🚀 Import').first.click()
        time.sleep(3)

        print("Attempting to directly click Manual Entry...")
        try:
            page.locator('button[data-baseweb="tab"]').filter(has_text='Manual Entry').click()
            time.sleep(1)
        except Exception as e:
            print(f"Could not click Manual Entry directly: {e}")

        print("Taking screenshot...")
        page.screenshot(path='verification/ux_screenshot.png')

        print("Done. Screenshot saved to verification/ux_screenshot.png")

        context.close()
        browser.close()

if __name__ == "__main__":
    main()
