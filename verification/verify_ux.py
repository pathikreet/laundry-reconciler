from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir="verification/videos/")
        page = context.new_page()
        page.goto("http://localhost:8501")

        # Wait for the app to load
        page.wait_for_selector("text=Import Wizard")
        print("Checking Import Data page...")
        page.screenshot(path="verification/import_page.png")

        print("Navigating to Run Reconciliation...")
        # Streamlit sidebar radio buttons: target the associated label via text
        page.locator('label').filter(has_text='Run Reconciliation').click()

        try:
            page.wait_for_selector("text=Reconciliation Engine", timeout=5000)
            print("Successfully navigated to Reconciliation Engine.")
        except:
            print("Failed to navigate. Taking debug screenshot.")
            page.screenshot(path="verification/debug_nav_fail.png")
            context.close()
            browser.close()
            return

        page.wait_for_timeout(1000)

        # Start Single Date Reconciliation
        print("Looking for Start Reconciliation button...")
        start_btn = page.locator("button").filter(has_text="▶️ Start Reconciliation")

        if start_btn.is_visible():
            print("Clicking Start Reconciliation button...")
            start_btn.click()

            # Wait for status container
            try:
                page.wait_for_selector("text=Reconciling Data...", timeout=5000)
                print("Status container found.")
            except:
                print("Status container not found immediately.")

            page.wait_for_timeout(2000)
            page.screenshot(path="verification/reconciliation_process.png")
        else:
            print("Start Reconciliation button not found. Taking debug screenshot.")
            page.screenshot(path="verification/debug_button_fail.png")

        # Test Date Range mode
        print("Switching to Date Range Mode...")
        page.locator('label').filter(has_text='📆 Date Range').click()
        page.wait_for_timeout(1000)

        range_start_btn = page.locator("button").filter(has_text="▶️ Start Range Reconciliation")
        if range_start_btn.is_visible():
            print("Clicking Start Range Reconciliation button...")
            range_start_btn.click()
            try:
                page.wait_for_selector("text=Reconciling Data Range...", timeout=5000)
                print("Range status container found.")
            except:
                print("Range status container not found immediately.")

            # Let it run for a bit
            page.wait_for_timeout(3000)
            page.screenshot(path="verification/range_reconciliation_process.png")
        else:
            print("Start Range Reconciliation button not found.")
            page.screenshot(path="verification/debug_range_button_fail.png")

        context.close()
        browser.close()

if __name__ == "__main__":
    run()
