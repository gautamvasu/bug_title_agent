## DefectLens — Bug Report Review Tool

DefectLens is a tool that reviews Phabricator bug reports for completeness and quality. It helps QA engineers and developers write better defect reports.

### What it does

- **Checklist Gap Analysis** — Checks your bug report against a checklist and highlights what's missing (red), partially covered (amber), or present (green)
- **Mandatory Tag Verification** — Verifies required tags are applied to the task, with wildcard support (e.g., `FoundBy*`, `*testing`)
- **Log Parsing** — Upload bugreport/logcat files — automatically extracts crashes, ANRs, exceptions, and tombstones
- **Defect Title Suggestions** — Suggests 3 clear, concise titles based on the description and log signals
- **Closed Task Detection** — Blocks review of already closed tasks
- **Google Chat Notification** — Send the review results directly to the task creator via Google Chat DM

### Three Review Modes

1. **Single Task** — Review one task at a time
2. **Multiple Tasks** — Paste multiple task numbers and review them all in one go
3. **All Open Tasks by Creator** — Enter a unixname, filter by date range, select tasks, and batch-review them

### Powered by

MetaGen (Llama) or Ollama (local) — no external API dependencies.

### How to get started

```
git clone https://github.com/gautamvasu/defectlens.git
cd defectlens
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.headless true
```

Opens at http://localhost:8501

### Contact

For questions or feedback, reach out to the DefectLens team.
