## 2026-02-23 - Progressive Disclosure for Long Processes
**Learning:** In Streamlit apps, sequential `st.info` messages for multi-step processes create clutter and don't effectively communicate progress. `st.status` containers provide a clean, collapsible way to show detailed progress without overwhelming the user, while still giving the crucial "something is happening" feedback.
**Action:** Use `st.status` for any process involving more than 2 distinct steps or taking > 3 seconds.

## 2026-02-23 - Streamlit File Uploaders and Previews
**Learning:** Adding a preview for `st.file_uploader` requires careful handling of the file pointer. The uploaded file is a stream; reading it for preview (e.g., with Pandas) consumes the stream. You MUST call `.seek(0)` both *before* reading the preview AND *after* finishing the preview, so that subsequent import logic receives a fresh stream. Failure to reset the pointer results in empty imports.
**Action:** Always wrap preview logic in a `try...finally` block where the `finally` clause executes `uploaded_file.seek(0)`.

## 2026-02-24 - Provide Data Previews
**Learning:** In data upload forms, users often doubt if they uploaded the correct file (especially with ambiguous names like "export.csv"). Providing a small, embedded preview of the data (e.g. first 5 rows) immediately after upload builds confidence before they commit to an import action.
**Action:** Use `st.expander` with `pd.read_csv` or `pd.read_excel` to show a snapshot of uploaded data, remembering to reset the file pointer (`.seek(0)`) to not break downstream logic.

## 2026-03-21 - Navigation Empty States and Streamlit Callbacks
**Learning:** Empty states with "dead-end" warning messages create friction. Providing a direct Call-to-Action (CTA) button to the next logical step (e.g., navigating to a data generation page) significantly improves flow. However, in Streamlit, directly mutating a widget's session state (like a sidebar navigation radio) *after* it has been rendered causes a fatal `StreamlitAPIException`. Navigation must be handled via `on_click` callbacks attached to buttons, rather than inline state mutation followed by `st.rerun()`.
**Action:** Replace dead-end warnings with `st.info` and a primary CTA button. Implement programmatic navigation using `on_click=navigate_to_callback` instead of setting `st.session_state` directly.

## 2026-04-17 - Required Field Indicators in Streamlit
**Learning:** Streamlit does not natively mark required fields visually, which is a major accessibility and usability issue for forms. Adding an asterisk to the label is helpful, but adding the `help="Required field"` parameter creates a standard tooltip icon that explicitly communicates the requirement to users and screen readers.
**Action:** Always append an asterisk `*` to the label and add `help="Required field"` to any required `st.text_input`, `st.number_input`, or `st.selectbox` fields.

## 2026-04-17 - Persistent Feedback in Clearing Forms
**Learning:** In Streamlit, when an action immediately triggers an `st.rerun()` (such as adding an item to a list and clearing the form fields), using `st.success()` provides a very poor UX because the message disappears instantly upon rerun. `st.toast()` correctly persists across the rerun, ensuring the user actually sees the feedback.
**Action:** Use `st.toast("Success message", icon="✅")` instead of `st.success()` for confirmation messages immediately preceding an `st.rerun()`.
