import sys
import os
import time

# Add root directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.sync_api import sync_playwright

def run_verification():
    os.makedirs('verification/videos', exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="verification/videos/",
            record_video_size={"width": 1280, "height": 720}
        )
        page = context.new_page()

        try:
            print("Navigating to Streamlit app...")
            page.goto("http://localhost:8501")
            page.wait_for_selector('div.stApp', timeout=10000)
            print("App loaded.")

            print("Navigating to Import Data page...")
            page.locator('label').filter(has_text="Import Data").click()
            time.sleep(1)

            print("Uploading CRM Sales dummy data to unlock steps...")

            page.locator('input[type="file"]').first.set_input_files('verification/dummy_sales.csv')
            time.sleep(1)
            page.get_by_role("button", name="🚀 Import").first.click()
            time.sleep(3)

            print("Opening Manual Entry tab...")
            page.locator('button').filter(has_text="Manual Entry").first.click()
            time.sleep(1)

            print("Capturing screenshot of required fields...")
            page.locator('div[data-testid="stExpander"]').filter(has_text="➕ Add Order Details").scroll_into_view_if_needed()
            time.sleep(1)
            page.screenshot(path="verification/notepad_required_fields.png")
            print("Screenshot saved to verification/notepad_required_fields.png")

        except Exception as e:
            print(f"Verification failed: {e}")
        finally:
            context.close()
            browser.close()
            print("Verification complete.")

if __name__ == "__main__":
    run_verification()
