from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto("http://localhost:8501")

        # Wait for the app to load
        page.wait_for_selector("text=Import Wizard")

        # Check Import Data page
        print("Checking Import Data page...")
        page.screenshot(path="verification/import_page.png")

        # Navigate to Run Reconciliation
        print("Navigating to Run Reconciliation...")
        # Streamlit sidebar radio buttons are labels.
        # We try to click the text 'Run Reconciliation'
        page.click("text=Run Reconciliation")

        # Wait for the header of the new page
        try:
            page.wait_for_selector("text=Reconciliation Engine", timeout=5000)
            print("Successfully navigated to Reconciliation Engine.")
        except:
            print("Failed to navigate. Taking debug screenshot.")
            page.screenshot(path="verification/debug_nav_fail.png")
            browser.close()
            return

        # Wait a bit for components to render
        page.wait_for_timeout(1000)

        # Click Start Reconciliation
        print("Looking for Start Reconciliation button...")
        # Use get_by_role for button
        start_btn = page.get_by_role("button", name="Start Reconciliation")

        if start_btn.is_visible():
            print("Clicking Start Reconciliation button...")
            start_btn.click()

            # Wait for status container
            try:
                # The status container header
                page.wait_for_selector("text=Running Reconciliation Engine...", timeout=5000)
                print("Status container found.")
            except:
                print("Status container not found immediately.")

            # Wait a bit for process to complete or error out
            page.wait_for_timeout(2000)

            # Take screenshot of the process/result
            page.screenshot(path="verification/reconciliation_process.png")
        else:
            print("Start Reconciliation button not found. Taking debug screenshot.")
            page.screenshot(path="verification/debug_button_fail.png")

        browser.close()

if __name__ == "__main__":
    run()
