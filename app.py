import os
import re
import subprocess
import json
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

SYSTEM_PROMPT = """You are a Bug Report Review Agent. Your job is to review a bug report and provide two things:

## Part 1: Checklist Gap Analysis
If a checklist is provided, compare the bug report (title, description, and logs) against each checklist item.
For EACH checklist item, output EXACTLY one of these formats (use the exact emoji and markdown):
- 🟢 **PRESENT**: <checklist item> — if fully covered
- 🟡 **PARTIALLY PRESENT**: <checklist item> — <what is missing or incomplete>
- 🔴 **MISSING**: <checklist item> — <what the reporter should add>

After listing all items, give an overall completeness score (e.g., "5/8 items covered").

IMPORTANT: If no log signals are provided in the input, always flag it as:
🔴 **MISSING**: Log attachment (bugreport/logcat) — No log file was attached. Please attach relevant logs for debugging.

If mandatory tag results are provided, include them as-is in your output under a "## Mandatory Tags" section before the checklist gap analysis.

If no checklist is provided, assess the bug report for common gaps: steps to reproduce, expected vs actual behavior, environment info, severity, log attachment, and screenshots, using the same color format above.

## Part 2: Suggested Defect Title
Analyze the description, logs, and all available context to suggest a title that clearly explains the intent and nature of the defect.

A good defect title should be:
- Clear: Anyone reading it should immediately understand the issue
- Concise: Short enough to scan quickly (ideally under 80 characters)
- Descriptive: Includes the WHAT (component/feature), the WHERE (context), and the problem
- Action-oriented: Describes the symptom or broken behavior, not the fix
- Specific: Avoids vague words like "issue", "problem", "bug", "broken", "not working"

When log signals (stack traces, crashes, ANRs) are provided, extract the component, exception type, and root cause to craft a precise title.

Provide:
1. Analysis of the current title's weaknesses
2. 3 improved title suggestions ranked from best to good. Format each suggestion EXACTLY as:
   💡 **SUGGESTION**: "<title here>"
3. A brief explanation of why the top suggestion best captures the defect's intent

Keep your response focused and practical."""

PROVIDERS = {
    "Groq (Free)": {
        "key_env": "GROQ_API_KEY",
        "placeholder": "gsk_...",
        "help": "Get a free key at https://console.groq.com/keys (no credit card needed)",
    },
    "Gemini (Free)": {
        "key_env": "GEMINI_API_KEY",
        "placeholder": "AIza...",
        "help": "Get a free key at https://aistudio.google.com/apikey",
    },
    "Claude (Paid)": {
        "key_env": "ANTHROPIC_API_KEY",
        "placeholder": "sk-ant-api03-...",
        "help": "Get your key at https://console.anthropic.com/settings/keys",
    },
}


def get_default_key(env_var):
    try:
        key = st.secrets.get(env_var, "")
    except Exception:
        key = ""
    if not key:
        key = os.environ.get(env_var, "")
    return key


def fetch_task_details(task_number):
    """Fetch task title, description, and creator from Meta Phabricator using jf CLI."""
    number = task_number.strip().lstrip("Tt")
    try:
        result = subprocess.run(
            [
                "jf", "graphql", "--query",
                f'{{ task(number: {number}) {{ name, task_description {{ text }}, task_creator {{ name, unixname }}, tags {{ nodes {{ name }} }} }} }}',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            task = data.get("task")
            if task:
                name = task.get("name", "")
                description = ""
                task_desc = task.get("task_description")
                if task_desc:
                    description = task_desc.get("text", "")
                creator = task.get("task_creator") or {}
                creator_name = creator.get("name", "")
                creator_unixname = creator.get("unixname", "")
                tags_nodes = (task.get("tags") or {}).get("nodes") or []
                tags = [t.get("name", "") for t in tags_nodes]
                return name, description, creator_name, creator_unixname, tags
        return None, None, None, None, []
    except Exception:
        return None, None, None, None, []


def send_gchat_message(unixname, message_text):
    """Send a Google Chat DM to a user using the gchat CLI."""
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(message_text)
            tmp_path = f.name
        result = subprocess.run(
            ["/opt/facebook/bin/gchat", "chat", "send", unixname, "--text-file", tmp_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        os.unlink(tmp_path)
        if result.returncode == 0:
            return True, "Message sent successfully"
        else:
            return False, f"gchat error: {result.stderr or result.stdout}"
    except FileNotFoundError:
        return False, "gchat CLI not found at /opt/facebook/bin/gchat"
    except subprocess.TimeoutExpired:
        return False, "gchat command timed out. Try again."
    except Exception as e:
        return False, f"Send failed: {e}"


def parse_log(log_text):
    """Extract key error signals from bugreport/logcat logs."""
    signals = []
    lines = log_text.splitlines()

    fatal_pattern = re.compile(r"(FATAL EXCEPTION|FATAL|AndroidRuntime|CRASH|panic|kernel panic)", re.IGNORECASE)
    anr_pattern = re.compile(r"(ANR in|Application Not Responding|Input dispatching timed out)", re.IGNORECASE)
    exception_pattern = re.compile(r"(Exception|Error|Throwable):\s*(.+)", re.IGNORECASE)
    tombstone_pattern = re.compile(r"(signal \d+ \(SIG\w+\)|Abort message:|backtrace:)", re.IGNORECASE)
    native_crash_pattern = re.compile(r"(DEBUG\s*:\s*pid:|*** *** *** *** *** ***)", re.IGNORECASE)

    context_window = 3
    for i, line in enumerate(lines):
        matched = False
        for pattern, label in [
            (fatal_pattern, "FATAL"),
            (anr_pattern, "ANR"),
            (native_crash_pattern, "NATIVE_CRASH"),
            (tombstone_pattern, "TOMBSTONE"),
        ]:
            if pattern.search(line):
                start = max(0, i - context_window)
                end = min(len(lines), i + context_window + 1)
                snippet = "\n".join(lines[start:end])
                signals.append(f"[{label}]\n{snippet}")
                matched = True
                break
        if not matched and exception_pattern.search(line):
            start = max(0, i)
            end = min(len(lines), i + 6)
            snippet = "\n".join(lines[start:end])
            signals.append(f"[EXCEPTION]\n{snippet}")

    # Deduplicate and limit
    seen = set()
    unique_signals = []
    for s in signals:
        key = s[:200]
        if key not in seen:
            seen.add(key)
            unique_signals.append(s)
        if len(unique_signals) >= 10:
            break

    return unique_signals


def check_mandatory_tags(mandatory_tags, actual_tags):
    """Compare mandatory tags against actual task tags. Returns formatted results."""
    if not mandatory_tags:
        return None
    actual_lower = {t.lower().strip() for t in actual_tags}
    results = []
    present_count = 0
    for tag in mandatory_tags:
        tag_clean = tag.strip()
        if not tag_clean:
            continue
        if tag_clean.lower() in actual_lower:
            results.append(f"- 🟢 **PRESENT**: Tag `{tag_clean}`")
            present_count += 1
        else:
            results.append(f"- 🔴 **MISSING**: Tag `{tag_clean}` — This mandatory tag is not applied to the task.")
    total = len([t for t in mandatory_tags if t.strip()])
    results.append(f"\nMandatory tags score: {present_count}/{total} present.")
    return "\n\n".join(results)


def build_user_prompt(task_number, current_title, description, log_summary=None, checklist=None, tags=None, mandatory_tag_results=None):
    prompt = f'Task Number: {task_number}\nCurrent Bug Title: "{current_title}"'
    if tags:
        prompt += f"\n\nTask Tags: {', '.join(tags)}"
    if description:
        prompt += f"\n\nTask Description:\n{description}"
    if log_summary:
        prompt += f"\n\nParsed Log Signals (extracted from attached bugreport/logcat):\n{log_summary}"
    if mandatory_tag_results:
        prompt += f"\n\nMandatory Tag Check Results (include as-is in output):\n{mandatory_tag_results}"
    if checklist:
        prompt += f"\n\nBug Report Checklist (required information):\n{checklist}"
    prompt += "\n\nPlease review this task: first show mandatory tag results (if any), then provide the checklist gap analysis, then suggest a defect title that clearly explains the intent of the defect based on the description and logs."
    return prompt


def call_groq(api_key, task_number, current_title, description, log_summary=None, checklist=None, tags=None, mandatory_tag_results=None):
    from groq import Groq

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(task_number, current_title, description, log_summary, checklist, tags, mandatory_tag_results)},
        ],
    )
    return response.choices[0].message.content


def call_gemini(api_key, task_number, current_title, description, log_summary=None, checklist=None, tags=None, mandatory_tag_results=None):
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = f'{SYSTEM_PROMPT}\n\n{build_user_prompt(task_number, current_title, description, log_summary, checklist, tags, mandatory_tag_results)}'
    response = model.generate_content(prompt)
    return response.text


def call_claude(api_key, task_number, current_title, description, log_summary=None, checklist=None, tags=None, mandatory_tag_results=None):
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": build_user_prompt(task_number, current_title, description, log_summary, checklist, tags, mandatory_tag_results)},
        ],
    )
    return message.content[0].text


CALL_FUNCTIONS = {
    "Groq (Free)": call_groq,
    "Gemini (Free)": call_gemini,
    "Claude (Paid)": call_claude,
}

st.set_page_config(page_title="DefectLens", page_icon="🔍", layout="centered")

st.markdown("""
<style>
    .stMarkdown strong {font-weight: 700;}
    div[data-testid="stButton"].notify-btn button {
        background-color: #198754 !important;
        color: white !important;
        border: none !important;
        padding: 0.5rem 1rem !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        border-radius: 0.5rem !important;
        width: 100% !important;
    }
    div[data-testid="stButton"].notify-btn button:hover {
        background-color: #146c43 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🔍 DefectLens")
st.markdown("Review a task for completeness against your checklist and get a better defect title based on description and logs.")

st.divider()

with st.sidebar:
    st.header("Settings")
    provider = st.selectbox("AI Provider", list(PROVIDERS.keys()))
    provider_config = PROVIDERS[provider]
    default_key = get_default_key(provider_config["key_env"])

    if default_key:
        st.success("API key configured by admin.")
        api_key = default_key
    else:
        api_key = st.text_input(
            "API Key",
            type="password",
            placeholder=provider_config["placeholder"],
            help=provider_config["help"],
        )
        if api_key:
            st.success("API key set!")
        else:
            st.info(f"Enter your API key. {provider_config['help']}")

task_number = st.text_input("Task Number", placeholder="T12345")

fetched_title = None
fetched_description = None
creator_name = None
creator_unixname = None
fetched_tags = []
if task_number:
    with st.spinner("Fetching task details..."):
        fetched_title, fetched_description, creator_name, creator_unixname, fetched_tags = fetch_task_details(task_number)
    if fetched_title:
        st.success(f"Fetched title: **{fetched_title}**")
    if creator_name:
        st.info(f"Creator: **{creator_name}** ({creator_unixname})")
    if fetched_description:
        with st.expander("Task Description (fetched)", expanded=False):
            st.text(fetched_description[:2000])

current_title = st.text_input(
    "Current Bug Title",
    value=fetched_title or "",
    placeholder="login not working",
    help="Auto-filled from task number, or enter manually",
)

description = st.text_area(
    "Bug Description (optional - helps generate better titles)",
    value=fetched_description or "",
    placeholder="Describe the bug in detail...",
    height=150,
    help="Auto-filled from task, or enter manually. More detail = better suggestions.",
)

st.subheader("Log Attachment")
uploaded_log = st.file_uploader(
    "Upload bugreport or logcat log file",
    type=["txt", "log", "zip", "gz"],
    help="Upload a bugreport or logcat file. The tool will parse it for errors, crashes, and ANRs to improve title suggestions.",
)

log_summary = None
if uploaded_log:
    try:
        if uploaded_log.name.endswith(".gz"):
            import gzip
            log_text = gzip.decompress(uploaded_log.read()).decode("utf-8", errors="replace")
        elif uploaded_log.name.endswith(".zip"):
            import zipfile
            import io
            with zipfile.ZipFile(io.BytesIO(uploaded_log.read())) as zf:
                text_parts = []
                for name in zf.namelist():
                    if any(kw in name.lower() for kw in ["logcat", "main", "system", "crash", "anr", "tombstone", "bugreport"]):
                        text_parts.append(zf.read(name).decode("utf-8", errors="replace"))
                log_text = "\n".join(text_parts) if text_parts else zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
        else:
            log_text = uploaded_log.read().decode("utf-8", errors="replace")

        signals = parse_log(log_text)
        if signals:
            log_summary = "\n\n".join(signals)
            st.success(f"Parsed {len(signals)} error signal(s) from log.")
            with st.expander("Parsed Log Signals", expanded=False):
                st.code(log_summary, language="text")
        else:
            st.info("No crash/error signals found in the log file.")
    except Exception as e:
        st.error(f"Failed to parse log file: {e}")

st.subheader("Bug Report Checklist")
checklist_source = st.radio(
    "Checklist source",
    ["Paste manually", "Upload file", "Google Sheet link"],
    horizontal=True,
)

checklist_text = None

if checklist_source == "Upload file":
    uploaded_checklist = st.file_uploader(
        "Upload checklist file",
        type=["txt", "md", "csv", "xlsx", "xls"],
        help="Upload a checklist file (.txt, .md, .csv, .xlsx) listing required information for a complete bug report.",
        key="checklist_uploader",
    )
    if uploaded_checklist:
        try:
            if uploaded_checklist.name.endswith((".xlsx", ".xls")):
                import pandas as pd
                df = pd.read_excel(uploaded_checklist)
                checklist_text = df.to_string(index=False)
            elif uploaded_checklist.name.endswith(".csv"):
                import pandas as pd
                df = pd.read_csv(uploaded_checklist)
                checklist_text = df.to_string(index=False)
            else:
                checklist_text = uploaded_checklist.read().decode("utf-8", errors="replace")
            st.success("Checklist loaded.")
            with st.expander("Checklist Contents", expanded=False):
                st.markdown(checklist_text)
        except Exception as e:
            st.error(f"Failed to read checklist: {e}")

elif checklist_source == "Google Sheet link":
    sheet_url = st.text_input(
        "Google Sheet URL",
        placeholder="https://docs.google.com/spreadsheets/d/...",
        help="Paste a Google Sheet link. The sheet must be accessible (shared within Meta).",
    )
    if sheet_url:
        try:
            import pandas as pd
            # Convert Google Sheet URL to CSV export URL
            if "/edit" in sheet_url:
                csv_url = sheet_url.split("/edit")[0] + "/export?format=csv"
            elif "/pubhtml" in sheet_url:
                csv_url = sheet_url.split("/pubhtml")[0] + "/export?format=csv"
            else:
                csv_url = sheet_url.rstrip("/") + "/export?format=csv"
            with st.spinner("Fetching Google Sheet..."):
                df = pd.read_csv(csv_url)
                checklist_text = df.to_string(index=False)
            st.success("Google Sheet loaded.")
            with st.expander("Checklist Contents", expanded=False):
                st.dataframe(df)
        except Exception as e:
            st.error(f"Failed to fetch Google Sheet: {e}. Make sure the sheet is shared/accessible.")

else:
    checklist_text = st.text_area(
        "Paste your checklist here",
        placeholder="- Steps to reproduce\n- Expected behavior\n- Actual behavior\n- Device/OS info\n- Screenshots/logs attached\n- Severity/priority\n- Build version",
        height=120,
        help="List the required information items for a complete bug report.",
    )
    if not checklist_text:
        checklist_text = None

st.subheader("Mandatory Tags")
tags_source = st.radio(
    "Mandatory tags source",
    ["Paste manually", "Upload file", "Google Sheet link"],
    horizontal=True,
    key="tags_source",
)

mandatory_tags_input = None

if tags_source == "Paste manually":
    mandatory_tags_input = st.text_area(
        "Enter mandatory tags (one per line)",
        placeholder="severity\ncomponent\nplatform\nteam\nproduct-area",
        height=120,
        help="List tags that must be present on every task. One tag per line.",
    )

elif tags_source == "Upload file":
    uploaded_tags = st.file_uploader(
        "Upload mandatory tags file",
        type=["txt", "md", "csv", "xlsx", "xls"],
        help="Upload a file with mandatory tags. One tag per line (txt/md) or one column (csv/xlsx).",
        key="tags_uploader",
    )
    if uploaded_tags:
        try:
            if uploaded_tags.name.endswith((".xlsx", ".xls")):
                import pandas as pd
                df = pd.read_excel(uploaded_tags)
                mandatory_tags_input = "\n".join(df.iloc[:, 0].dropna().astype(str).tolist())
            elif uploaded_tags.name.endswith(".csv"):
                import pandas as pd
                df = pd.read_csv(uploaded_tags)
                mandatory_tags_input = "\n".join(df.iloc[:, 0].dropna().astype(str).tolist())
            else:
                mandatory_tags_input = uploaded_tags.read().decode("utf-8", errors="replace")
            st.success("Mandatory tags loaded.")
        except Exception as e:
            st.error(f"Failed to read tags file: {e}")

else:
    tags_sheet_url = st.text_input(
        "Google Sheet URL for mandatory tags",
        placeholder="https://docs.google.com/spreadsheets/d/...",
        help="Paste a Google Sheet link. First column will be used as tag names.",
        key="tags_sheet_url",
    )
    if tags_sheet_url:
        try:
            import pandas as pd
            if "/edit" in tags_sheet_url:
                csv_url = tags_sheet_url.split("/edit")[0] + "/export?format=csv"
            elif "/pubhtml" in tags_sheet_url:
                csv_url = tags_sheet_url.split("/pubhtml")[0] + "/export?format=csv"
            else:
                csv_url = tags_sheet_url.rstrip("/") + "/export?format=csv"
            with st.spinner("Fetching Google Sheet..."):
                df = pd.read_csv(csv_url)
                mandatory_tags_input = "\n".join(df.iloc[:, 0].dropna().astype(str).tolist())
            st.success("Mandatory tags loaded from Google Sheet.")
        except Exception as e:
            st.error(f"Failed to fetch Google Sheet: {e}")

mandatory_tags = [t.strip() for t in mandatory_tags_input.splitlines() if t.strip()] if mandatory_tags_input else []

if st.button("Review Task", type="primary", use_container_width=True):
    if not api_key:
        st.warning("Please enter your API key in the sidebar.")
    elif not task_number or not current_title:
        st.warning("Please enter both a task number and title.")
    else:
        with st.spinner("Generating better titles..."):
            try:
                mtr = check_mandatory_tags(mandatory_tags, fetched_tags) if mandatory_tags else None
                result = CALL_FUNCTIONS[provider](api_key, task_number, current_title, description, log_summary, checklist_text, fetched_tags, mtr)
                st.divider()
                st.subheader(f"Review for {task_number}")
                # Color-code the checklist results
                colored = result.replace(
                    "🔴 **MISSING**", '<span style="color:#dc3545;font-weight:bold;">🔴 MISSING</span>**'
                ).replace(
                    "🟢 **PRESENT**", '<span style="color:#198754;font-weight:bold;">🟢 PRESENT</span>**'
                ).replace(
                    "🟡 **PARTIALLY PRESENT**", '<span style="color:#d4930d;font-weight:bold;">🟡 PARTIALLY PRESENT</span>**'
                ).replace(
                    "💡 **SUGGESTION**", '<span style="color:#0d6efd;font-weight:bold;">💡 SUGGESTION</span>**'
                )
                st.markdown(colored, unsafe_allow_html=True)

                # Store result for notification
                st.session_state["last_review_result"] = result
                st.session_state["last_task_number"] = task_number
                st.session_state["last_creator_unixname"] = creator_unixname
                st.session_state["last_creator_name"] = creator_name
            except Exception as e:
                st.error(f"Error: {e}")

# Notify creator button (shown after review)
if st.session_state.get("last_review_result") and st.session_state.get("last_creator_unixname"):
    st.divider()
    notify_creator = st.session_state.get("last_creator_name") or st.session_state["last_creator_unixname"]
    st.markdown('<style>div[data-testid="stButton"]:last-of-type button {background-color: #198754 !important; color: white !important; border: none !important; padding: 0.5rem 1rem !important; font-size: 1rem !important; font-weight: 600 !important; border-radius: 0.5rem !important;}</style>', unsafe_allow_html=True)
    if st.button(f"Notify {notify_creator} on Google Chat", type="primary", use_container_width=True):
        task_num = st.session_state["last_task_number"]
        review = st.session_state["last_review_result"]
        # Build a plain-text message for Google Chat
        gchat_msg = f"Hi! Your task {task_num} has been reviewed by DefectLens.\n\n{review}"
        with st.spinner("Sending Google Chat message..."):
            success, msg = send_gchat_message(
                st.session_state["last_creator_unixname"],
                gchat_msg,
            )
        if success:
            st.success(f"Notified {notify_creator} on Google Chat!")
        else:
            st.error(f"Failed to notify: {msg}")

st.divider()
st.caption("DefectLens — Powered by Groq, Google Gemini & Claude AI")
