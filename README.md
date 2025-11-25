# CV Analyzer — Streamlit Prototype (Groq)

This prototype is a user-friendly Streamlit app to test CV extraction, scoring, and AI summarization
(using Groq) before building the full Next.js + Supabase product.

## Files
- `app.py` — Main Streamlit app
- `requirements.txt` — Python dependencies

## How to run locally
1. Create a Python virtualenv and activate it:
```bash
python3 -m venv venv
source venv/bin/activate
```
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Set your Groq API key as an environment variable (do not commit this to git):
```bash
export GROQ_API_KEY="gsk_..."
# Optional: specify model (default used if not set)
export GROQ_MODEL="llama3-70b-8192"
```
4. Run the app:
```bash
streamlit run app.py
```
5. Open the local URL printed by Streamlit in your browser and upload a CV PDF.
6. In the sidebar, enable "Use AI for summary (Groq)" and run scoring.

## Streamlit Cloud / Streamlit Community Cloud
If you deploy to Streamlit Cloud, add `GROQ_API_KEY` as a secret in the app settings (App → Settings → Secrets) with key `GROQ_API_KEY`.

## Webhook integration
You can enter an n8n webhook URL in the sidebar and enable "Auto POST results to webhook" to send JSON results after scoring.
The app uses header `x-webhook-secret` with value from env `N8N_WEBHOOK_SECRET` (defaults to `dev-secret`).

## Notes & privacy
- Do not send real candidate PII to third-party APIs without consent and understanding of data usage policies.
- This is a prototype intended for testing features and validating workflows only.
