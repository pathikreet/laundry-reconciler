from playwright.sync_api import sync_playwright, expect
import time

def verify_empty_states():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir="verification/videos/")
        page = context.new_page()

        try:
            # Wait for streamlit to start up
            time.sleep(3)
            page.goto("http://localhost:8501")

            # Wait for main app to load
            expect(page.get_by_text("Laundry Reconciler").first).to_be_visible(timeout=10000)

            # 1. Verify View Results empty state navigation
            page.get_by_text("View Results").click()
            expect(page.get_by_text("Reconciliation Dashboard").first).to_be_visible()

            btn_results = page.locator('button').filter(has_text="Go to Run Reconciliation")
            expect(btn_results).to_be_visible()

            # Take a screenshot
            page.screenshot(path="verification/fixed_empty_results.png")

            # Click it and verify navigation occurs without crash
            btn_results.click()
            expect(page.get_by_text("⚙️ Reconciliation Engine").first).to_be_visible(timeout=10000)

            # 2. Verify History empty state navigation
            page.get_by_text("History").click()
            expect(page.get_by_text("📜 Reconciliation History").first).to_be_visible(timeout=10000)

            btn_history = page.locator('button').filter(has_text="Go to Run Reconciliation")
            expect(btn_history).to_be_visible()

            # Take a screenshot
            page.screenshot(path="verification/fixed_empty_history.png")

            # Click it and verify navigation occurs without crash
            btn_history.click()
            expect(page.get_by_text("⚙️ Reconciliation Engine").first).to_be_visible(timeout=10000)
            print("Successfully verified empty state navigation without crash.")

        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    verify_empty_states()
