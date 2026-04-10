# DefectLens

A tool that reviews bug reports for completeness and suggests better defect titles. It checks your task against a checklist, verifies mandatory tags, parses logs for error signals, and notifies the creator on Google Chat about gaps found.

Powered by **MetaGen & Llama** — fully internal, no external API dependencies.

## Features

- **Three Review Modes:**
  - **Single Task** — Review one task at a time with full details.
  - **Multiple Tasks** — Paste multiple task numbers and review them all in one go.
  - **All Open Tasks by Creator** — Enter a unixname to fetch all open tasks created by that person, filter by date range, select which ones to review, and batch-review them.
- **Checklist Gap Analysis** — Compare bug reports against a configurable checklist. Missing items flagged in red, partial in amber, present in green.
- **Mandatory Tag Check** — Define required tags with wildcard support (`FoundBy*`, `*testing`) and verify they are applied to the task.
- **Log Parsing** — Upload bugreport/logcat files (.txt, .log, .gz, .zip). Automatically extracts crashes, ANRs, exceptions, and tombstones.
- **Defect Title Suggestions** — Suggests clear, concise titles based on description and log signals.
- **Closed Task Detection** — Automatically checks if a task is closed and blocks review of closed tasks.
- **Google Chat Notification** — Send review results directly to the task creator via Google Chat DM.
- **Auto-fetch from Phabricator** — Pulls task title, description, creator, status, and tags from Phabricator using `jf`.
- **AI Providers** — MetaGen (Internal) or Ollama (Local, no API key needed).

## Setup

1. **Clone the repo and create a virtual environment:**
   ```bash
   cd defectlens
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Choose your AI provider:**

   **MetaGen (Internal — recommended):**
   - Connect to VPN
   - Visit https://metagen-llm-api-keys.nest.x2p.facebook.net/
   - Click **"Create API Key"**
   - Create a MetaGen entitlement and link it to your Llama API App ID (see [MetaGen docs](https://www.internalfb.com/wiki/MetaGen/Getting_Started/MetaGen_for_Researchers/) for details)
   - Add your key to `.env`:
     ```
     METAGEN_API_KEY=your-key-here
     ```

   **Ollama (Local — no API key needed):**
   - Download & install from [ollama.com/download](https://ollama.com/download)
   - Pull the model: `ollama pull llama3.1:8b`
   - Make sure Ollama is running before using DefectLens

## Usage

```bash
source venv/bin/activate
streamlit run app.py --server.headless true
```
Opens at `http://localhost:8501`.

## How It Works

1. **Choose a review mode:**
   - **Single Task** — Enter a task number to review one task.
   - **Multiple Tasks** — Paste multiple task numbers (one per line).
   - **All Open Tasks by Creator** — Enter a creator's unixname, filter by date range (7/14/30/60/90/180 days or all time), and select tasks to review.
2. **Upload a log file** (optional) — Bugreport or logcat files are parsed for crash/error signals.
3. **Provide a checklist** (optional) — Paste, upload a file (.txt, .csv, .xlsx), or link a Google Sheet.
4. **Define mandatory tags** (optional) — Paste, upload, or link a Google Sheet with required tags.
   - Supports wildcard matching: `FoundBy*` matches any tag starting with "FoundBy", `*testing` matches any tag ending with "testing".
5. **Click "Review Task(s)"** — Get a full review with:
   - Mandatory tag check (present/missing) with wildcard support
   - Checklist gap analysis with color-coded results
   - Suggested defect titles in bold blue
   - Progress bar for multi-task reviews
6. **Notify creator** — Send the review to the task creator on Google Chat with one click (per task).

## Example Output

```
## Mandatory Tags
Mandatory tags score: 1/2 present (50%)
- PRESENT: Tag `severity`
- MISSING: Tag `platform` — This mandatory tag is not applied to the task.

## Checklist Gap Analysis
Overall completeness score: 1/3 items covered (33%)
- PRESENT: Steps to reproduce
- MISSING: Expected vs actual behavior — Please describe what should happen and what actually happens.
- MISSING: Log attachment (bugreport/logcat) — No log file was attached.

## Suggested Defect Title
SUGGESTION: "Camera preview freezes on Pixel 8 after switching to video mode"
```

## Requirements

- Python 3.9+
- VPN (for MetaGen API access) or Ollama installed locally
- `jf` CLI (for Phabricator integration)
- `gchat` CLI at `/opt/facebook/bin/gchat` (for Google Chat notifications)

## Oncall

Please connect in case of any issues/suggestions.
