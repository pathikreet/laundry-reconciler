## 2026-02-23 - Progressive Disclosure for Long Processes
**Learning:** In Streamlit apps, sequential `st.info` messages for multi-step processes create clutter and don't effectively communicate progress. `st.status` containers provide a clean, collapsible way to show detailed progress without overwhelming the user, while still giving the crucial "something is happening" feedback.
**Action:** Use `st.status` for any process involving more than 2 distinct steps or taking > 3 seconds.

## 2026-03-01 - File Preview Pattern
**Learning:** For file imports in data-heavy apps, users hesitate to click "Import" without verification. A lightweight preview using `st.expander` with the first 5 rows builds trust and reduces anxiety about incorrect file uploads.
**Action:** Always implement a `preview_uploaded_file` helper for file uploaders, ensuring file pointer reset (`seek(0)`) to prevent stream consumption errors.
