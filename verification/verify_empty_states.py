from playwright.sync_api import sync_playwright, expect
import time

def verify_empty_states():
    with sync_playwright() as p:
        # We need to record a video as per AGENTS.md / memory
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir="verification/videos/")
        page = context.new_page()

        try:
            # Wait for streamlit to start up
            time.sleep(3)
            page.goto("http://localhost:8501")

            # Wait for main app to load
            expect(page.get_by_text("Digital Accountant").first).to_be_visible(timeout=10000)

            # 1. Verify View Results empty state
            # When clicking radio buttons in sidebar, use the label locator as per memory
            page.locator('label').filter(has_text='View Results').click()
            page.wait_for_selector('text="📊 Reconciliation Dashboard"', timeout=10000)
            expect(page.get_by_text("📊 Reconciliation Dashboard").first).to_be_visible()

            # Check for the new info message and button
            expect(page.locator('text="No reconciliation runs found. You need to run reconciliation first."').first).to_be_visible(timeout=10000)
            btn_results = page.locator('button').filter(has_text="Go to Run Reconciliation")
            expect(btn_results.first).to_be_visible()

            # Take a screenshot of the View Results empty state
            page.screenshot(path="verification/empty_results.png")

            # Click it to ensure it navigates
            btn_results.click()

            # Navigate to History page
            page.locator('label').filter(has_text='History').click()
            expect(page.get_by_text("📜 Reconciliation History").first).to_be_visible(timeout=10000)

            # Check for the new info message and button
            expect(page.get_by_text("No reconciliation history yet.")).to_be_visible()
            btn_history = page.locator('button').filter(has_text="Go to Run Reconciliation")
            expect(btn_history).to_be_visible()

            # Take a screenshot of the History empty state
            page.screenshot(path="verification/empty_history.png")

            # Click it to ensure it navigates
            btn_history.click()

        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    verify_empty_states()
