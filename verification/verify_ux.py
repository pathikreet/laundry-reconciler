import sys
import os
from playwright.sync_api import sync_playwright, expect

def verify_app():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Go to app
        page.goto("http://localhost:8501")

        # Give more time to load Streamlit components
        page.wait_for_selector('div.stApp', timeout=15000)
        page.wait_for_timeout(5000)

        # Take a screenshot of the main page
        page.screenshot(path="verification/app_home.png", full_page=True)

        browser.close()

if __name__ == "__main__":
    verify_app()
