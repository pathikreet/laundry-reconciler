from playwright.sync_api import Page, expect, sync_playwright
import time
import re

def verify_feature(page: Page):
    page.goto("http://localhost:8501")
    page.wait_for_timeout(2000)

    # Click on Run Reconciliation
    page.locator('label').filter(has_text='Run Reconciliation').click()
    page.wait_for_timeout(2000)

    # Switch to Date Range
    page.locator('label').filter(has_text='Date Range').click()
    page.wait_for_timeout(1000)

    # Click Start Range Reconciliation
    page.locator('button', has_text='Start Range Reconciliation').click()
    page.wait_for_timeout(5000)

    # Click View Results
    page.locator('button', has_text='View Results').click()
    page.wait_for_timeout(3000)

    # Switch to Date Range view mode
    page.locator('label').filter(has_text='Date Range').click()
    page.wait_for_timeout(2000)

    # Wait for the "Showing results for" info message or "No reconciliation runs found" message
    # And check for our new button if there are no runs

    # Verify we're on View Results page
    expect(page.locator("h2").filter(has_text="Reconciliation Dashboard")).to_be_visible()

    page.screenshot(path="verification/verification.png")
    page.wait_for_timeout(1000)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir="verification/video")
        page = context.new_page()
        try:
            verify_feature(page)
        finally:
            context.close()
            browser.close()
