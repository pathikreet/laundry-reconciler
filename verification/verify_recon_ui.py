import time
from playwright.sync_api import Page, expect, sync_playwright

def verify_recon_ui(page: Page):
    print("Navigating to app...")
    page.goto("http://localhost:8501")

    print("Waiting for sidebar navigation...")
    # Click "Run Reconciliation" in the sidebar
    # We use label selector as per memory guideline for Streamlit radio buttons
    run_recon_radio = page.locator('label').filter(has_text='Run Reconciliation')
    run_recon_radio.click()

    print("Waiting for page load...")
    # Wait for the main area header to appear to ensure page loaded
    expect(page.locator("h2").filter(has_text="Reconciliation Engine")).to_be_visible()

    print("Taking before screenshot...")
    page.screenshot(path="verification/recon_before.png")

    print("Clicking Start Reconciliation...")
    # Click "Start Reconciliation" button
    start_btn = page.locator("button").filter(has_text="Start Reconciliation")
    start_btn.click()

    print("Waiting for process to finish...")
    # Wait for the status block to show complete or the success message to appear
    # The success message is rendered outside the status block now
    expect(page.locator("div[data-testid='stAlert']").filter(has_text="Reconciliation Complete!")).to_be_visible(timeout=10000)

    print("Taking after screenshot...")
    page.screenshot(path="verification/recon_after.png")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # Give Streamlit a moment to start up
            time.sleep(3)
            verify_recon_ui(page)
            print("Verification script completed successfully.")
        except Exception as e:
            print(f"Verification failed: {e}")
            page.screenshot(path="verification/recon_error.png")
        finally:
            browser.close()
