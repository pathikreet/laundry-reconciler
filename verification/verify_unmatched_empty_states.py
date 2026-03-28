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

            # 1. Run Reconciliation
            page.get_by_text("Run Reconciliation").click()
            expect(page.get_by_text("⚙️ Reconciliation Engine").first).to_be_visible()

            # Click start
            start_btn = page.locator("button").filter(has_text="▶️ Start Reconciliation")
            start_btn.click()

            # Wait for completion
            expect(page.get_by_text("✅ Reconciliation Complete!")).to_be_visible(timeout=10000)

            # Click view results
            page.locator("button").filter(has_text="📊 View Results").click()

            # Wait for View Results to load
            expect(page.get_by_text("📊 Reconciliation Dashboard").first).to_be_visible(timeout=10000)

            # Click Unmatched tab
            page.get_by_text("❓ Unmatched").click()
            time.sleep(1) # wait for tab content to render

            # Verify the info states
            expect(page.get_by_text("🎉 All notepad entries successfully matched to orders. No action needed.")).to_be_visible()
            expect(page.get_by_text("🎉 All MSWIPE entries successfully matched to orders. No action needed.")).to_be_visible()

            # Take a screenshot
            page.screenshot(path="verification/unmatched_empty_states.png")
            print("Successfully verified Unmatched tab empty states.")

        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    verify_empty_states()
