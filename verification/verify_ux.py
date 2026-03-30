from playwright.sync_api import sync_playwright

def verify_dashboard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # 1. Go to the local Streamlit app
            page.goto("http://localhost:8501")

            # Wait for Streamlit to load its initial state
            page.wait_for_selector("text=Laundry Reconciler", timeout=10000)

            # 2. Check if Dashboard is the active/default page
            # Based on our changes, the Dashboard should load by default.
            page.wait_for_selector("text=Reconciliation Dashboard", timeout=5000)

            # 3. Check for the "Import Data" button on the empty state Dashboard
            import_button = page.locator("button").filter(has_text="Import Data")
            import_button.wait_for(state="visible", timeout=5000)

            # 4. Take a screenshot of the Dashboard landing page
            page.screenshot(path="verification/dashboard_landing.png", full_page=True)
            print("Successfully verified Dashboard is the landing page.")

            # 5. Click the "Import Data" button to ensure it navigates correctly
            import_button.click()

            # Wait for the Import Wizard page to load
            page.wait_for_selector("text=Import Wizard", timeout=5000)

            # Take a screenshot of the Import Wizard page
            page.screenshot(path="verification/import_wizard.png", full_page=True)
            print("Successfully navigated to Import Wizard.")

        except Exception as e:
            print(f"Verification failed: {e}")
            page.screenshot(path="verification/error_state.png", full_page=True)
            raise e
        finally:
            browser.close()

if __name__ == "__main__":
    verify_dashboard()
