## 2026-02-23 - Progressive Disclosure for Long Processes
**Learning:** In Streamlit apps, sequential `st.info` messages for multi-step processes create clutter and don't effectively communicate progress. `st.status` containers provide a clean, collapsible way to show detailed progress without overwhelming the user, while still giving the crucial "something is happening" feedback.
**Action:** Use `st.status` for any process involving more than 2 distinct steps or taking > 3 seconds.

## 2026-02-23 - Streamlit File Uploaders and Previews
**Learning:** Adding a preview for `st.file_uploader` requires careful handling of the file pointer. The uploaded file is a stream; reading it for preview (e.g., with Pandas) consumes the stream. You MUST call `.seek(0)` both *before* reading the preview AND *after* finishing the preview, so that subsequent import logic receives a fresh stream. Failure to reset the pointer results in empty imports.
**Action:** Always wrap preview logic in a `try...finally` block where the `finally` clause executes `uploaded_file.seek(0)`.
