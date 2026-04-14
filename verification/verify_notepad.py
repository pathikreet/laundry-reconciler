from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir="verification/videos/")
        page = context.new_page()
        page.goto("http://localhost:8501")

        # Wait for the app to load
        page.wait_for_selector("text=Import Wizard")

        # Unlock notepad step by bypassing CRM sales (for testing purposes, we assume it's unlocked or we just interact with it if visible)
        # Actually, let's just upload a dummy file to CRM sales to unlock it
        with open("dummy.csv", "w") as f:
            f.write("Payment Date,Customer Name,Amount,Payment Mode\n2025-11-01,Test,100,Cash")

        page.locator('input[type="file"]').first.set_input_files('dummy.csv')
        page.wait_for_timeout(1000)
        page.locator("button").filter(has_text="🚀 Import").first.click()
        page.wait_for_timeout(2000)

        # Now scroll down and open manual entry tab
        page.locator('button[data-baseweb="tab"]').filter(has_text="✍️ Manual Entry").click()
        page.wait_for_timeout(1000)

        # Expand the "Add Order Details" if not already expanded
        expander = page.locator('div[data-testid="stExpander"]').filter(has_text="➕ Add Order Details")
        if not expander.locator('label').filter(has_text="Delivery Date *").is_visible():
            expander.click()
            page.wait_for_timeout(500)

        # Take screenshot of the form showing asterisks
        page.screenshot(path="verification/notepad_form.png")
        print("Took screenshot of the notepad form.")

        # Add an entry to test toast
        page.locator('input[aria-label="Order Number *"]').fill("T123")
        page.locator('input[aria-label="Amount Collected (₹) *"]').fill("150")

        page.locator("button").filter(has_text="➕ Add Order Details").click()
        page.wait_for_timeout(500) # Wait for toast to appear

        page.screenshot(path="verification/notepad_toast.png")
        print("Took screenshot of the toast notification.")

        context.close()
        browser.close()

if __name__ == "__main__":
    run()
