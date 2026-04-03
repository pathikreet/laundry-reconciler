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

## 2026-04-03 - Mocking UI Imports in Pytest
**Learning:** When using Pytest to test Streamlit UI module loading by patching `sys.modules['streamlit']`, the UI module under test is aggressively cached by Python across runs/files. This causes false negative `AssertionError` failures (e.g. `mock.set_page_config.assert_called()`) because the code is not re-executed when imported a second time.
**Action:** Ensure the UI module is explicitly removed from `sys.modules` (`if 'src.ui.app' in sys.modules: del sys.modules['src.ui.app']`) right before the `import src.ui.app` call in the test suite so it executes freshly against the mocked environment.

## 2026-04-03 - Persistent Form Success Notifications
**Learning:** In data entry forms, triggering `st.success` immediately followed by `st.rerun()` prevents the user from reading the success message, as it flashes momentarily and vanishes.
**Action:** Use `st.toast` with an appropriate icon within form submission callbacks to present non-blocking notifications that persist smoothly across reruns, improving visual feedback without hijacking space.
