from playwright.sync_api import sync_playwright
import os
import time

def run():
    print("Starting verification...")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("Navigating to app...")
        # Assuming app is running on localhost:8501
        try:
            page.goto("http://localhost:8501", timeout=10000)
        except Exception as e:
            print(f"Failed to load app: {e}")
            return

        # Wait for the app to load
        try:
            page.wait_for_selector("text=Import Wizard", timeout=10000)
            print("App loaded successfully.")
        except Exception as e:
            print("Import Wizard header not found.")
            page.screenshot(path="verification/debug_load_fail.png")
            return

        # Path to sample file
        sample_file = os.path.abspath("sample/SalesAndDeliveryCRMExport-November.xlsx")
        if not os.path.exists(sample_file):
            print(f"Sample file not found at {sample_file}")
            return

        print(f"Uploading file: {sample_file}")

        # Upload file to the first file uploader (CRM)
        # Streamlit file uploader input is usually hidden, but we can target input[type=file]
        try:
            # There are multiple file inputs. CRM is the first one.
            file_input = page.locator('input[type="file"]').nth(0)
            file_input.set_input_files(sample_file)
            print("File uploaded.")
        except Exception as e:
            print(f"Failed to upload file: {e}")
            page.screenshot(path="verification/debug_upload_fail.png")
            return

        # Wait for "Preview Data" expander to appear
        # The expander summary usually contains the text
        try:
            # We look for the text we added in the expander header
            # "Preview Data (SalesAndDeliveryCRMExport-November.xlsx)"
            preview_text = "Preview Data (SalesAndDeliveryCRMExport-November.xlsx)"
            page.wait_for_selector(f"text={preview_text}", timeout=10000)
            print("Preview expander found!")

            # Take a screenshot
            page.screenshot(path="verification/preview_success.png")
            print("Screenshot saved to verification/preview_success.png")

        except Exception as e:
            print(f"Preview expander not found: {e}")
            page.screenshot(path="verification/debug_preview_fail.png")

        browser.close()

if __name__ == "__main__":
    run()
