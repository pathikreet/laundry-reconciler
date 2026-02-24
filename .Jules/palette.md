## 2026-02-23 - Progressive Disclosure for Long Processes
**Learning:** In Streamlit apps, sequential `st.info` messages for multi-step processes create clutter and don't effectively communicate progress. `st.status` containers provide a clean, collapsible way to show detailed progress without overwhelming the user, while still giving the crucial "something is happening" feedback.
**Action:** Use `st.status` for any process involving more than 2 distinct steps or taking > 3 seconds.

## 2026-05-24 - Pre-Import Data Previews
**Learning:** Uploading files without seeing the content creates anxiety about whether the correct file was chosen. Providing a small preview (first 5 rows) inside an expander immediately after upload gives users confidence and reduces import errors without cluttering the UI.
**Action:** Always add a collapsible data preview for file uploaders before the primary action button.
