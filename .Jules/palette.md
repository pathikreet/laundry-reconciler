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

## 2026-03-25 - Avoid Direct Session State Mutation for Navigation
**Learning:** Mutating `st.session_state` keys that govern application routing directly within conditional blocks (and then calling `st.rerun()`) results in `StreamlitAPIException` because the framework complains about modifying the state of a widget after it has been instantiated.
**Action:** Consistently use the `on_click` parameter of buttons combined with a helper function (like `navigate_to`) and `args` to trigger navigation state changes.
