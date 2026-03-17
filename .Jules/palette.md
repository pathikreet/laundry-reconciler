## 2026-02-23 - Progressive Disclosure for Long Processes
**Learning:** In Streamlit apps, sequential `st.info` messages for multi-step processes create clutter and don't effectively communicate progress. `st.status` containers provide a clean, collapsible way to show detailed progress without overwhelming the user, while still giving the crucial "something is happening" feedback.
**Action:** Use `st.status` for any process involving more than 2 distinct steps or taking > 3 seconds.

## 2026-02-23 - Streamlit File Uploaders and Previews
**Learning:** Adding a preview for `st.file_uploader` requires careful handling of the file pointer. The uploaded file is a stream; reading it for preview (e.g., with Pandas) consumes the stream. You MUST call `.seek(0)` both *before* reading the preview AND *after* finishing the preview, so that subsequent import logic receives a fresh stream. Failure to reset the pointer results in empty imports.
**Action:** Always wrap preview logic in a `try...finally` block where the `finally` clause executes `uploaded_file.seek(0)`.

## 2026-02-24 - Provide Data Previews
**Learning:** In data upload forms, users often doubt if they uploaded the correct file (especially with ambiguous names like "export.csv"). Providing a small, embedded preview of the data (e.g. first 5 rows) immediately after upload builds confidence before they commit to an import action.
**Action:** Use `st.expander` with `pd.read_csv` or `pd.read_excel` to show a snapshot of uploaded data, remembering to reset the file pointer (`.seek(0)`) to not break downstream logic.

## 2026-03-17 - Progress Indicator Metrics Placement
**Learning:** When using `st.status` for progressive disclosure of long-running multi-step processes, it is crucial to place final success messages, summary metrics, and subsequent action buttons *outside* the `with st.status(...):` block. If placed inside, these important final results become hidden when the status container automatically collapses (`expanded=False`) upon completion, leading to a confusing UX where the user thinks the process finished but doesn't see the results.
**Action:** Always structure code so that the `with st.status()` block only contains the transient progress updates, and the final state/metrics are rendered immediately after the block exits.
