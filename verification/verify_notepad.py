from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir="verification/videos/")
        page = context.new_page()
        page.goto("http://localhost:8501")

        print("Waiting for Notepad component...")
        page.wait_for_selector("text=Step 5: Runner Notepad")

        print("Switching to Manual Entry tab...")
        page.locator('button[role="tab"]').filter(has_text='✍️ Manual Entry').click()

        print("Filling out the form...")
        page.fill('input[placeholder="e.g. T697"]', "T123")
        page.fill('input[aria-label="Amount Collected (₹)"]', "500")

        print("Submitting the form...")
        page.locator('button').filter(has_text="➕ Add Order Details").click()

        # Wait to ensure the toast appears and form resets
        page.wait_for_timeout(2000)

        # Verify the entry is listed in the table
        try:
            # Switch back to manual entry tab because it might reset context based on default tab
            page.locator('button[role="tab"]').filter(has_text='✍️ Manual Entry').click()
            page.wait_for_timeout(500)

            # Use a more robust selector to wait for visibility since it found hidden ones
            page.wait_for_selector("td:has-text('T123')", state="visible", timeout=5000)
            print("Successfully found added entry T123 in the queued list.")

            page.screenshot(path="verification/notepad_form_success2.png")
        except Exception as e:
            print("Failed to find the entry. Form submission might have failed.", e)
            page.screenshot(path="verification/notepad_form_failure2.png")

        context.close()
        browser.close()

if __name__ == "__main__":
    run()
