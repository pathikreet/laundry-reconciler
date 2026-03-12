from playwright.sync_api import sync_playwright, expect
import time
import os

def test_streamlit_ui(page):
    page.goto("http://localhost:8501")

    # Wait for Streamlit app to load
    page.wait_for_selector("text=Laundry Reconciler")

    # 1. Verify title
    expect(page.get_by_role("heading", name="🧺 Laundry Reconciler")).to_be_visible()

    # Take screenshot of the main page
    page.screenshot(path="verification/main_page.png")

    # 2. Navigate to "Run Reconciliation" to verify status block
    page.locator("label").filter(has_text="Run Reconciliation").click()
    page.wait_for_selector("text=Reconciliation Engine")

    # Take screenshot of the empty reconciliation page
    page.screenshot(path="verification/recon_page_before.png")

    # Start reconciliation
    page.get_by_role("button", name="▶️ Start Reconciliation").click()

    # Wait for it to finish
    page.wait_for_selector("text=Reconciliation Complete!", timeout=10000)

    # The status should be collapsed, and metrics should be visible
    expect(page.locator("text=Notepad Matches").first).to_be_visible()

    page.screenshot(path="verification/recon_page_after.png")

    print("UI tests passed!")

if __name__ == "__main__":
    # Create verification directory if it doesn't exist
    os.makedirs("verification", exist_ok=True)

    # Give Streamlit a moment to start up
    time.sleep(3)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            test_streamlit_ui(page)
        except Exception as e:
            print(f"Test failed: {e}")
            page.screenshot(path="verification/error_screenshot.png")
            raise
        finally:
            browser.close()
