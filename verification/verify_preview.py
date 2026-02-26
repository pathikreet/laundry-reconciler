import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            print("Navigating to app...")
            page.goto("http://localhost:8501")

            # Wait for app to load
            # Streamlit sometimes takes a while to render the first time
            page.wait_for_selector("text=Import Wizard", timeout=20000)
            print("App loaded.")

            # Create a dummy file for upload
            with open("verification/dummy_crm.csv", "w") as f:
                f.write("Order Number,Customer Name,Order Date,Order Amount,Payment Amount\nORD001,John Doe,2023-01-01,100,100\nORD002,Jane Doe,2023-01-02,200,0")

            # Find the file uploader for CRM
            # Streamlit file uploader is an input[type=file]
            # There are multiple, the first one is CRM

            print("Uploading file...")

            # Wait for file input to be attached
            page.wait_for_selector("input[type='file']", state='attached', timeout=10000)

            file_input = page.locator("input[type='file']").first
            file_input.set_input_files("verification/dummy_crm.csv")

            print("File uploaded. Waiting for preview...")
            # Wait for "Preview dummy_crm.csv" text
            # Use a slightly longer timeout as Streamlit re-runs the script
            page.wait_for_selector("text=Preview dummy_crm.csv", timeout=15000)

            # Expand the preview (it defaults to expanded=False)
            # Find the expander summary/button and click it
            # The expander header usually contains the text
            page.click("text=Preview dummy_crm.csv")

            # Wait a bit for animation/table render
            time.sleep(2)

            print("Taking screenshot...")
            page.screenshot(path="verification/preview_screenshot.png")
            print("Screenshot saved.")

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="verification/error_screenshot.png")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
