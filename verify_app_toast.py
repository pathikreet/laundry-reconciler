import asyncio
from playwright.async_api import async_playwright
import time
import os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(record_video_dir="verification/videos/")
        page = await context.new_page()

        print("Navigating to app...")
        await page.goto("http://localhost:8501")
        await page.wait_for_selector("text=Laundry Reconciler")

        print("Uploading dummy_crm.xlsx...")
        # Find file uploader
        file_input = await page.query_selector("input[type='file']")
        await file_input.set_input_files("dummy_crm.xlsx")

        # Wait for preview text
        print("Waiting for upload to process...")
        await page.wait_for_selector("text=Preview first", timeout=10000)

        print("Clicking Import button...")
        save_btn = await page.query_selector("button:has-text('Import')")

        if save_btn:
            await save_btn.click()
            print("Clicked import, waiting a short moment for toast...")

            # Wait a brief moment for toast to appear
            await page.wait_for_timeout(500)

            # Take screenshot of the toast in action
            os.makedirs("verification", exist_ok=True)
            screenshot_path = "verification/app_toast.png"
            # Scroll up to see the toast at the bottom right
            await page.evaluate("window.scrollTo(0, 0)")
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot saved to {screenshot_path}")

            # Wait a bit longer to see if it stays
            await page.wait_for_timeout(1500)
            await page.screenshot(path="verification/app_toast_after_rerun.png")

        else:
            print("Could not find save button, taking debug screenshot")
            os.makedirs("verification", exist_ok=True)
            await page.screenshot(path="verification/app_debug.png")

        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
