# Agentic Capabilities & Missing Features Suggestions

Based on a review of the Digital Accountant app and its workflow, here are several suggestions for introducing agentic capabilities and new features to further reduce manual effort and improve the intelligence of the system.

## 1. Intelligent OCR & Data Extraction Agent
Currently, the OCR parsing for the Runner Notepad is an external shell script relying on `gemini-cli`.
* **Suggestion:** Integrate an autonomous Data Extraction Agent directly into the application.
* **How it works:** Users could upload raw photos of notepads (or even WhatsApp screenshots of payments) directly into the Streamlit UI. The agent would asynchronously process the images, infer missing column headers, correct spelling mistakes in names using fuzzy matching against the CRM database, and structure the data without requiring the user to run CLI commands.

## 2. Automated Exception Follow-up Agent
Reconciliation currently flags exceptions (e.g., `CreditPolicyViolation`, `DeliveredNotMarkedCRM`) for manual review.
* **Suggestion:** Introduce an agent that drafts and optionally sends follow-up communications.
* **How it works:** For a `CreditPolicyViolation`, the agent could draft a WhatsApp message or SMS to the customer requesting the pending payment. For `DeliveredNotMarkedCRM`, it could notify the specific store manager via a Slack/Teams webhook to update the CRM.

## 3. Trend Analysis & Anomaly Detection Agent
The current dashboard provides static period summaries.
* **Suggestion:** Implement an analytical agent that proactively monitors trends and alerts on anomalies.
* **How it works:** The agent could analyze historical reconciliation runs to identify patterns like "Store X has a 30% higher rate of CashUndeposited exceptions on weekends" or "Runner Y frequently forgets to log Paytm payments." It would generate an executive summary report with these insights, transforming the tool from a purely operational dashboard into a strategic advisory system.

## 4. Smart Mapping Resolution Agent
The `MatchingService` currently relies on static fuzzy matching thresholds.
* **Suggestion:** Introduce a reinforcement learning or LLM-backed agent to assist with difficult matching edge-cases.
* **How it works:** When an order cannot be confidently matched, the agent reviews context (e.g., looking at common misspellings, partial amounts across multiple days, or cross-referencing with other unlinked MSWIPE transactions) and proposes a match with a natural language explanation (e.g., "Matched 'Jhn Doe' to 'John Doe' because the amount exactly matches the outstanding balance of order T123 on that same date"). The user's acceptance or rejection of the proposal trains the agent for future runs.

## 5. Agentic Chat Interface (Co-Pilot)
Information density in the dashboard can be overwhelming.
* **Suggestion:** Instead of building a full standalone chat interface, develop a reusable "Skill" (e.g., leveraging MCP or APIs) that integrates the Digital Accountant with existing chat interfaces like Gemini, ChatGPT, Claude, or Grok.
* **How it works:** This skill would expose the app's data models and query logic (e.g., fetching exceptions, querying order status) to external LLMs. Users could then interact with their preferred chat tool to ask questions like "Show me all orders from last week where cash was missing" or "Why was order T450 flagged?", while keeping the conversation grounded in actual database context without reinventing the chat UI.
