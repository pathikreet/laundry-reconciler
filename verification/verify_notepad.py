from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir="verification/videos/")
        page = context.new_page()
        page.goto("http://localhost:8502")

        page.wait_for_timeout(2000)

        # Click "Manual Entry" tab
        page.locator('button', has_text='✍️ Manual Entry').first.click()
        page.wait_for_timeout(1000)

        # Look for the required label
        label = page.locator('label', has_text='Order Number *').first
        if label.is_visible():
            print("Successfully found 'Order Number *' label.")
        else:
            print("Failed to find 'Order Number *' label.")

        # Try finding using exact match or checking visible state after rerender
        page.screenshot(path="verification/notepad_debug1.png")

        page.locator('input[aria-label="Order Number *"]').first.fill('TEST123')
        page.wait_for_timeout(500)

        page.locator('input[aria-label="Customer Name (optional)"]').first.fill('John Doe')
        page.wait_for_timeout(500)

        page.screenshot(path="verification/notepad_form_filled.png")

        # Submit - use expander context since there might be multiple buttons
        # Streamlit button text is in a <p> or <div> inside the <button>
        # Just find the button that contains exactly "➕ Add Order Details"
        add_btn = page.locator('button', has_text='➕ Add Order Details').filter(has_not=page.locator('div[data-testid="stExpander"] button')).first

        try:
            add_btn.click(timeout=5000)
        except Exception as e:
            print(f"Failed to click add button directly: {e}")
            # Try clicking by exact structure
            page.locator('div[data-testid="stButton"] button').filter(has_text='Add Order Details').first.click()

        page.wait_for_timeout(2000)

        page.screenshot(path="verification/notepad_form_submitted.png")

        # Verify fields are cleared
        order_val = page.locator('input[aria-label="Order Number *"]').first.input_value()
        customer_val = page.locator('input[aria-label="Customer Name (optional)"]').first.input_value()

        if order_val == '' and customer_val == '':
            print("Fields were successfully cleared!")
        else:
            print(f"Fields were NOT cleared. Order: '{order_val}', Customer: '{customer_val}'")

        context.close()
        browser.close()

if __name__ == "__main__":
    run()
