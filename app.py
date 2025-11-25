import streamlit as st
from io import BytesIO
import PyPDF2
import os
import json
import re
import base64
from datetime import datetime
import requests

# Try to import Groq SDK. If not installed, the app will show a warning when AI is used.
try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except Exception:
    GROQ_SDK_AVAILABLE = False

st.set_page_config(page_title='CV Analyzer — Prototype (Groq)', layout='wide', initial_sidebar_state='expanded')

# --- Custom CSS for warm gradient and MacOS-like card UI ---
st.markdown(
    """
    <style>
    :root{
      --bg-gradient-start: #fff6f0;
      --bg-gradient-end: #fff0e6;
      --card-bg: rgba(255, 255, 255, 0.92);
      --accent: #ff6b6b;
      --muted: #6b7280;
    }
    html, body, .main {
      background: linear-gradient(180deg, var(--bg-gradient-start) 0%, var(--bg-gradient-end) 100%);
      color: #111827;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    }
    .stApp .block-container {
      padding-top: 1.5rem;
      padding-left: 2rem;
      padding-right: 2rem;
      padding-bottom: 2rem;
      max-width: 1100px;
      margin: 0 auto;
    }
    .card {
      background: var(--card-bg);
      border-radius: 14px;
      box-shadow: 0 8px 20px rgba(0,0,0,0.06);
      padding: 16px;
      margin-bottom: 16px;
    }
    .header-left {
      display:flex;
      align-items:center;
      gap:12px;
    }
    .logo-circle {
      width:54px;height:54px;border-radius:12px;background:linear-gradient(135deg,#ff9a9e,#fecfef);display:flex;align-items:center;justify-content:center;
      font-weight:700;color:white;font-size:20px;
    }
    .muted { color: var(--muted); }
    .small { font-size:13px; }
    .btn-download { background: linear-gradient(90deg,#ff7a59,#ffb28a); border: none; color: white; padding: 8px 12px; border-radius: 8px; text-decoration:none; }
    pre { white-space: pre-wrap; word-wrap: break-word; }
    </style>
    """, unsafe_allow_html=True
)

# --- Header ---
with st.container():
    st.markdown('<div class="card header-left">', unsafe_allow_html=True)
    cols = st.columns([0.11, 0.89])
    with cols[0]:
        st.markdown('<div class="logo-circle">CV</div>', unsafe_allow_html=True)
    with cols[1]:
        st.markdown("<h2 style='margin:0 0 6px 0'>CV Analyzer — Prototype (Groq)</h2>", unsafe_allow_html=True)
        st.markdown("<div class='muted small'>Upload a CV, get a fast AI/heuristic summary & score. Use this to validate workflows before building the full product.</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Sidebar controls
with st.sidebar:
    st.markdown("### Quick Actions")
    st.markdown("Upload a file on the main UI to start.")
    show_example = st.button("Load Example CV")
    st.markdown("---")
    st.markdown("### Integration")
    webhook_url = st.text_input("n8n Webhook URL (optional)", placeholder="https://your-n8n-domain/webhook/cv-processor")
    post_results = st.checkbox("Auto POST results to webhook", value=False)
    st.markdown("---")
    st.markdown("### AI Options (Groq)")
    use_ai = st.checkbox("Use AI for summary (Groq)", value=False)
    st.markdown("If using AI, set environment variable GROQ_API_KEY and optionally GROQ_MODEL (default: llama3-70b-8192).", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("Prototype UI — not for production. Do not send real PII without consent.")

# Helper functions
def extract_text_from_pdf_bytes(file_bytes):
    try:
        reader = PyPDF2.PdfReader(BytesIO(file_bytes))
    except Exception:
        return ""
    text_chunks = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ''
        except Exception:
            text = ''
        text_chunks.append(text)
    return "\n\n".join(text_chunks).strip()

def simple_score(cv_text, job_description):
    score = 0
    reasons = []
    if not cv_text:
        return {'overall': 0, 'details': ['No text extracted']}
    # experience proxy: years mentioned
    yrs = 0
    yrs_matches = re.findall(r'(\d+)\s+years?', cv_text, flags=re.IGNORECASE)
    if yrs_matches:
        try:
            yrs = max(int(x) for x in yrs_matches)
        except:
            yrs = 0
    if yrs >= 8:
        score += 30
        reasons.append(f'Experience >= {yrs} years (+30)')
    elif yrs >= 3:
        score += 18
        reasons.append(f'Experience >= {yrs} years (+18)')
    else:
        reasons.append('Limited explicit years experience (+0)')
    # skill match
    keywords = ['python','sql','excel','hr','recruit','communication','aws','nlp','pandas','javascript','data analysis','talent']
    hits = 0
    for k in keywords:
        if k.lower() in cv_text.lower():
            hits += 1
    skill_score = min(35, hits * 6)
    score += skill_score
    reasons.append(f'Skills keywords matched: {hits} (+{skill_score})')
    # education (simple)
    lower = cv_text.lower()
    if 'master' in lower or 'msc' in lower:
        score += 15
        reasons.append('Postgraduate degree detected (+15)')
    elif 'bachelor' in lower or 'bsc' in lower or 'ba ' in lower:
        score += 8
        reasons.append('Bachelor degree detected (+8)')
    # achievements check
    if 'award' in lower or 'published' in lower or 'patent' in lower:
        score += 10
        reasons.append('Notable achievements detected (+10)')
    overall = max(0, min(100, score))
    return {'overall': overall, 'details': reasons}

def generate_download_link(obj, filename='result.json'):
    b = json.dumps(obj, indent=2).encode('utf-8')
    b64 = base64.b64encode(b).decode()
    href = f'<a download="{filename}" href="data:application/json;base64,{b64}" class="btn-download">Download result JSON</a>'
    return href

# Groq helper
def groq_summarize(cv_text, model=None, max_tokens=400, temperature=0.2):
    """
    Summarize CV using Groq SDK. Requires GROQ_API_KEY env var.
    model default is taken from GROQ_MODEL env var or fallback to 'llama3-70b-8192'.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set. Set environment variable before using AI.")
    chosen_model = model or os.getenv("GROQ_MODEL") or "llama3-70b-8192"
    if not GROQ_SDK_AVAILABLE:
        raise RuntimeError("groq SDK not installed. Add 'groq' to requirements and pip install it.")

    client = Groq(api_key=api_key)
    prompt = f"""Summarize this CV in concise bullet points:
- Name (if present)
- Total experience (years)
- Key skills (comma-separated)
- Education
- Notable achievements
- Suggested seniority level (junior / mid / senior / lead)

CV:
{cv_text[:4000]}
"""

    # Use the chat completions API via the SDK
    resp = client.chat.completions.create(
        model=chosen_model,
        messages=[{"role":"user","content":prompt}],
        max_tokens=max_tokens,
        temperature=temperature
    )

    # Extract text from common response shapes
    try:
        # SDK often returns choices -> choices[0].message.content or similar
        if hasattr(resp, "choices") and len(resp.choices) > 0:
            # try several access patterns
            choice = resp.choices[0]
            if hasattr(choice, "message") and isinstance(choice.message, dict) and "content" in choice.message:
                return choice.message["content"].strip()
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                return choice.message.content.strip()
            if hasattr(choice, "text"):
                return choice.text.strip()
        # fallback to stringified response
        return str(resp)[:3000]
    except Exception:
        return str(resp)[:3000]

# Main UI
uploaded_file = st.file_uploader('Upload CV (PDF)', type=['pdf'], accept_multiple_files=False)

if show_example:
    sample_text = """John Doe
Senior Data Analyst
Experience: 6 years at Company X, 2 years at Company Y
Skills: Python, SQL, Pandas, Excel, Communication, Reporting
Education: Bachelor of Science in Computer Science
Achievements: Published market analysis in Local Journal
"""
    extracted_text = sample_text
    st.success("Loaded example CV (plain-text).")
else:
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        with st.spinner('Extracting text from PDF...'):
            extracted_text = extract_text_from_pdf_bytes(file_bytes)
    else:
        extracted_text = ""

if not extracted_text:
    st.info("Upload a CV PDF to extract text. Use the example CV from the sidebar for a quick demo.")

# Layout: left - main, right - summary
col1, col2 = st.columns([1.3, 0.9])

with col1:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### CV Text")
    if extracted_text:
        st.text_area("", value=extracted_text, height=360)
    else:
        st.markdown("<div class='muted small'>No text extracted yet.</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### Job Description (for scoring)")
    default_jd = "Data Analyst with Python and SQL, 3+ years experience"
    job_desc = st.text_area("Paste a job description to score the candidate against", value=default_jd, height=140)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    if st.button('Run Scoring & Summary'):
        if not extracted_text:
            st.error("No CV text available to analyze. Upload a PDF or load the example.")
        else:
            with st.spinner('Scoring...'):
                heuristic = simple_score(extracted_text, job_desc)
                # Optional: AI summary (if enabled)
                ai_summary = None
                if use_ai:
                    try:
                        ai_summary = groq_summarize(extracted_text, model=os.getenv('GROQ_MODEL'))
                    except Exception as e:
                        st.warning('Groq call failed: ' + str(e))
                        ai_summary = None
                result_obj = {
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'job_description': job_desc,
                    'scores': heuristic,
                    'ai_summary': ai_summary,
                    'cv_excerpt': extracted_text[:2000]
                }
            st.success('Scoring complete. See the right column for results.')
            # auto post to webhook if enabled
            if post_results and webhook_url:
                try:
                    headers = {'Content-Type':'application/json', 'x-webhook-secret': os.getenv('N8N_WEBHOOK_SECRET','dev-secret')}
                    resp = requests.post(webhook_url, json=result_obj, headers=headers, timeout=15)
                    if resp.status_code in (200,201,204):
                        st.info('Results posted to webhook successfully.')
                    else:
                        st.warning(f'Webhook returned status {resp.status_code}: {resp.text[:200]}')
                except Exception as e:
                    st.error('Failed to POST to webhook: ' + str(e))
            # store last result to session_state for the right panel to show
            st.session_state['last_result'] = result_obj
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### Quick Summary")
    if 'last_result' in st.session_state:
        r = st.session_state['last_result']
        st.metric("Overall Score", f"{r['scores']['overall']} / 100")
        if r.get('ai_summary'):
            st.markdown("**AI Summary:**")
            st.write(r['ai_summary'])
        st.markdown("**Reasons / Breakdown:**")
        for d in r['scores']['details']:
            st.write("- " + d)
        st.markdown("**CV Excerpt:**")
        st.write(r['cv_excerpt'][:800])
        st.markdown(generate_download_link(r, filename='cv_result.json'), unsafe_allow_html=True)
    else:
        st.markdown("<div class='muted small'>No results yet. Run scoring to see a summary.</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown('---')
st.markdown('Built for testing workflows — move to Next.js + Supabase for production.')
