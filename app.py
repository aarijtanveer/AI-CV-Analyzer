
import streamlit as st
import os
from io import BytesIO
import PyPDF2
import json
import re
import base64
from datetime import datetime
import requests

# --- Load secrets (st.secrets preferred on Streamlit Cloud) ---
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
GROQ_MODEL = st.secrets.get("GROQ_MODEL") or os.getenv("GROQ_MODEL") or "llama3-70b-8192"
N8N_WEBHOOK_SECRET = st.secrets.get("N8N_WEBHOOK_SECRET") or os.getenv("N8N_WEBHOOK_SECRET") or "dev-secret"

# Try to import Groq SDK
try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except Exception:
    GROQ_SDK_AVAILABLE = False

st.set_page_config(page_title='CV Analyzer — Prototype (Groq)', layout='wide', initial_sidebar_state='expanded')

# --- Custom CSS ---
st.markdown("""
<style>
:root{
  --bg-gradient-start: #fff6f0;
  --bg-gradient-end: #fff0e6;
  --card-bg: rgba(255, 255, 255, 0.92);
}
html, body, .main {
  background: linear-gradient(180deg, var(--bg-gradient-start), var(--bg-gradient-end));
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial;
}
.card { background: var(--card-bg); padding: 16px; border-radius: 14px; box-shadow: 0 8px 20px rgba(0,0,0,0.06); margin-bottom: 14px; }
.logo-circle { width:54px;height:54px;border-radius:12px;background:linear-gradient(135deg,#ff9a9e,#fecfef);display:flex;align-items:center;justify-content:center;font-weight:700;color:white;font-size:20px; }
.btn-download { background: linear-gradient(90deg,#ff7a59,#ffb28a); color:white; padding:8px 12px; border-radius:8px; text-decoration:none; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
with st.container():
    st.markdown('<div class="card" style="display:flex; gap:12px; align-items:center;">', unsafe_allow_html=True)
    st.markdown('<div class="logo-circle">CV</div>', unsafe_allow_html=True)
    st.markdown("<h2>CV Analyzer — Prototype (Groq)</h2>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### Quick Actions")
    show_example = st.button("Load Example CV")
    st.markdown("---")
    webhook_url = st.text_input("n8n Webhook URL (optional)")
    post_results = st.checkbox("POST results to webhook", False)
    st.markdown("---")
    use_ai = st.checkbox("Use AI (Groq)", False)
    st.markdown("Requires GROQ_API_KEY in Streamlit Secrets.")
    st.markdown("---")
    st.markdown("Prototype — not for production.")

# Functions
def extract_text_from_pdf_bytes(file_bytes):
    try:
        reader = PyPDF2.PdfReader(BytesIO(file_bytes))
    except Exception:
        return ""
    text = []
    for p in reader.pages:
        try:
            text.append(p.extract_text() or "")
        except:
            text.append("")
    return "\n".join(text)

def simple_score(cv, jd):
    score = 0
    notes = []
    yrs = re.findall(r"(\\d+)\\s+years?", cv.lower())
    if yrs:
        y = max(int(x) for x in yrs)
        if y >= 8:
            score += 30; notes.append(f"Experience {y}y (+30)")
        elif y >= 3:
            score += 18; notes.append(f"Experience {y}y (+18)")
        else:
            notes.append("Limited experience")
    kws = ["python","sql","excel","hr","recruit","communication","aws","nlp","pandas","javascript"]
    hits = sum(k in cv.lower() for k in kws)
    score += min(35, hits*6)
    notes.append(f"Skill hits: {hits}")
    if "master" in cv.lower(): score+=15; notes.append("Masters (+15)")
    elif "bachelor" in cv.lower(): score+=8; notes.append("Bachelor (+8)")
    if "award" in cv.lower(): score+=10; notes.append("Achievements (+10)")
    return {"overall": min(score,100), "details": notes}

def generate_download_link(obj):
    b = json.dumps(obj, indent=2).encode()
    href = f'<a download="result.json" href="data:application/json;base64,{base64.b64encode(b).decode()}" class="btn-download">Download JSON</a>'
    return href

def groq_summarize(cv_text):
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY missing in st.secrets.")
    if not GROQ_SDK_AVAILABLE:
        raise RuntimeError("groq SDK missing. Add to requirements.")
    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"Summarize this CV:\n{cv_text[:4000]}"
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role":"user","content":prompt}],
        max_tokens=400
    )
    return resp.choices[0].message["content"].strip()

# Main UI
uploaded_file = st.file_uploader("Upload CV PDF", type=["pdf"])

if show_example:
    extracted_text = "John Doe, Data Analyst, 6 years..."
else:
    extracted_text = extract_text_from_pdf_bytes(uploaded_file.read()) if uploaded_file else ""

col1, col2 = st.columns([1.3,0.7])

with col1:
    st.markdown('<div class="card"><h4>CV Text</h4>', unsafe_allow_html=True)
    st.text_area("", extracted_text, height=350)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><h4>Job Description</h4>', unsafe_allow_html=True)
    jd = st.text_area("Job Description", "Data Analyst with Python and SQL", height=150)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("Run Scoring & Summary"):
        if not extracted_text:
            st.error("No CV text found.")
        else:
            score = simple_score(extracted_text, jd)
            ai_summary = None
            if use_ai:
                try:
                    ai_summary = groq_summarize(extracted_text)
                except Exception as e:
                    st.warning(str(e))
            result = {
                "timestamp": datetime.utcnow().isoformat()+"Z",
                "scores": score,
                "ai_summary": ai_summary,
                "cv_excerpt": extracted_text[:1200]
            }
            st.session_state["result"] = result

            if post_results and webhook_url:
                try:
                    requests.post(webhook_url, json=result, headers={"x-webhook-secret":N8N_WEBHOOK_SECRET}, timeout=10)
                    st.success("Posted to webhook.")
                except Exception as e:
                    st.error(str(e))

with col2:
    st.markdown('<div class="card"><h4>Summary</h4>', unsafe_allow_html=True)
    if "result" in st.session_state:
        r = st.session_state["result"]
        st.metric("Score", f"{r['scores']['overall']} / 100")
        if r["ai_summary"]:
            st.markdown("### AI Summary")
            st.write(r["ai_summary"])
        st.markdown("### Breakdown")
        for d in r["scores"]["details"]:
            st.write("- " + d)
        st.markdown(generate_download_link(r), unsafe_allow_html=True)
    else:
        st.write("Run scoring to see output.")
    st.markdown('</div>', unsafe_allow_html=True)
