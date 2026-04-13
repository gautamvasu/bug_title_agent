# DefectLens — Product Requirements Document

**Author:** Vasu Gautam
**Date:** April 2026
**Status:** Active
**Version:** 1.0

---

## 1. Overview

DefectLens is an AI-powered bug report review tool that helps QA engineers and developers write higher-quality defect reports. It analyzes Phabricator tasks against configurable checklists, verifies mandatory tags, parses log files for error signals, and suggests clearer defect titles — all through a web-based interface powered by Streamlit.

## 2. Problem Statement

Bug reports filed in Phabricator often suffer from:

- **Incomplete information** — missing reproduction steps, expected vs. actual behavior, environment details, or log attachments
- **Poor titles** — vague titles like "login not working" that don't convey the component, symptom, or context
- **Missing tags** — mandatory tags (severity, platform, found-by source) are frequently omitted, making triage and tracking harder
- **No feedback loop** — creators don't learn what's missing until a reviewer manually points it out, often days later

These gaps slow down triage, increase back-and-forth, and reduce the signal-to-noise ratio in defect backlogs.

## 3. Goals

| Goal | Success Metric |
|------|---------------|
| Improve bug report completeness | Increase average checklist coverage score across reviewed tasks |
| Reduce review turnaround time | Provide instant automated review instead of waiting for manual reviewer |
| Standardize defect quality | Consistent checklist and tag enforcement across teams |
| Close the feedback loop | Notify creators immediately via Google Chat with actionable gaps |

## 4. Non-Goals

- Automatically editing or closing Phabricator tasks
- Replacing human code review or manual QA judgment
- Providing root-cause analysis or debugging suggestions
- Supporting non-Phabricator issue trackers

## 5. Target Users

| Persona | Use Case |
|---------|----------|
| **QA Engineers** | Review their own or teammates' bug reports before handoff to engineering |
| **QA Leads / Managers** | Batch-review all open tasks by a specific creator to audit report quality |
| **Developers** | Quickly assess incoming bug reports for completeness before investing in investigation |

## 6. Features & Requirements

### 6.1 Review Modes

| Mode | Description | Priority |
|------|-------------|----------|
| **Single Task** | Enter one task number; auto-fetches title, description, creator, tags, and status from Phabricator | P0 |
| **Multiple Tasks** | Paste multiple task numbers (one per line); each is reviewed independently with a progress bar | P0 |
| **All Open Tasks by Creator** | Enter a unixname, filter by date range (7/14/30/60/90/180 days or all time), select tasks, and batch-review | P1 |

### 6.2 Checklist Gap Analysis

- Compare the bug report's content against a configurable checklist
- Each item is rated: **PRESENT** (green), **PARTIALLY PRESENT** (amber), or **MISSING** (red)
- An overall completeness score (X/Y items, Z%) is displayed
- Checklist input methods: paste manually, upload file (.txt, .csv, .xlsx), or link a Google Sheet
- If no checklist is provided, a default assessment covers: steps to reproduce, expected vs. actual behavior, environment info, severity, log attachment, and screenshots

### 6.3 Mandatory Tag Verification

- Define required tags that must be applied to every task
- Supports wildcard matching (`FoundBy*` matches any tag starting with "FoundBy"; `*testing` matches any tag ending with "testing")
- Each tag is reported as PRESENT or MISSING
- A mandatory tags score (X/Y present, Z%) is displayed
- Tag input methods: paste manually, upload file, or link a Google Sheet

### 6.4 Log Parsing

- Upload bugreport or logcat files (.txt, .log, .gz, .zip)
- Automatically extracts and categorizes: FATAL exceptions, ANRs, native crashes, tombstones, and general exceptions
- Provides context (surrounding lines) for each signal
- Deduplicates signals and caps at 10 to keep LLM context manageable
- Parsed signals are included in the AI review prompt for better title suggestions

### 6.5 Defect Title Suggestions

- Generates 3 ranked title suggestions based on the task description, current title, and parsed log signals
- Each suggestion follows best practices: clear, concise (<80 chars), specific component + symptom + context
- Includes analysis of the current title's weaknesses and rationale for the top suggestion

### 6.6 Closed Task Detection

- Automatically checks task status via Phabricator API
- Blocks review of closed tasks with a warning message
- In batch mode, closed tasks are skipped and listed separately

### 6.7 Google Chat Notification

- One-click notification to send review results to the task creator via Google Chat DM
- Message is formatted for gchat (bold, plain text, no HTML)
- Uses the `gchat` CLI at `/opt/facebook/bin/gchat`
- Available per-task in both single and multi-task review modes

### 6.8 CLI Tool

- Standalone CLI (`defectlens_cli.py`) for quick title suggestions without the web UI
- Supports single-shot (`defectlens_cli.py <task> <title>`) and interactive modes
- Uses Claude API (Anthropic SDK) for generation

## 7. Architecture

### 7.1 Components

```
+-------------------+     +------------------+     +-----------------+
|   Streamlit UI    |---->|   app.py         |---->|  Phabricator    |
|   (Browser)       |     |  (Core Logic)    |     |  (jf CLI)       |
+-------------------+     +------------------+     +-----------------+
                               |        |
                               v        v
                    +----------+   +----------+
                    | MetaGen  |   |  Ollama   |
                    | (Llama)  |   |  (Local)  |
                    +----------+   +----------+
                               |
                               v
                    +-------------------+
                    |  gchat CLI        |
                    |  (Notifications)  |
                    +-------------------+
```

### 7.2 AI Providers

| Provider | Model | API | Use Case |
|----------|-------|-----|----------|
| **MetaGen (Internal)** | Llama-4-Scout-17B-16E-Instruct-FP8 | `api.llama.com/compat/v1/chat/completions` | Primary — requires VPN and API key |
| **Ollama (Local)** | llama3.1:8b | `localhost:11434/api/chat` | Offline / no API key — runs on local machine |

### 7.3 External Dependencies

| Dependency | Purpose |
|------------|---------|
| `jf` CLI | Phabricator GraphQL queries (task details, user lookup, task search) |
| `gchat` CLI | Google Chat DM notifications |
| MetaGen API | LLM inference (internal) |
| Ollama | LLM inference (local) |

## 8. Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit 1.56+ |
| Language | Python 3.9+ |
| AI/LLM | MetaGen (Llama) / Ollama |
| Data | Phabricator (via `jf` GraphQL) |
| Notifications | Google Chat (via `gchat` CLI) |
| Dependencies | streamlit, pandas, openpyxl, python-dotenv, markdown |

## 9. User Flow

1. **Select review mode** — Single Task, Multiple Tasks, or All Open Tasks by Creator
2. **Enter task number(s)** — Task details are auto-fetched from Phabricator
3. **Upload log file** (optional) — Bugreport/logcat parsed for error signals
4. **Provide checklist** (optional) — Paste, upload, or link a Google Sheet
5. **Define mandatory tags** (optional) — Paste, upload, or link a Google Sheet
6. **Click "Review Task(s)"** — AI analyzes the task and returns:
   - Mandatory tag check results
   - Checklist gap analysis with color-coded scores
   - 3 suggested defect titles with rationale
7. **Notify creator** (optional) — Send results to the task creator on Google Chat

## 10. Constraints & Assumptions

- Users have access to Meta's internal network (VPN) for MetaGen and Phabricator
- The `jf` CLI is installed and authenticated
- The `gchat` CLI is available at `/opt/facebook/bin/gchat` for notifications
- LLM responses are capped at 1024 tokens to keep reviews focused
- Log parsing extracts at most 10 signals to stay within LLM context limits
- Google Sheets used for checklists/tags must be shared/accessible

## 11. Future Considerations

- **Auto-attach review to Phabricator task** — Post the review as a comment on the task itself
- **Team dashboards** — Aggregate completeness scores across teams over time
- **Custom scoring weights** — Allow teams to weight checklist items differently
- **Integration with CI/CD** — Trigger reviews automatically when tasks are created or updated
- **Historical trend analysis** — Track improvement in bug report quality per creator over time
- **Additional notification channels** — Workplace, email, or Phabricator Herald rules
