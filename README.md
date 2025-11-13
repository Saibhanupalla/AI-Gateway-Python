# AI Gateway — Streamlit Frontend

This repository contains a simple Streamlit frontend that connects to the FastAPI backend in the same workspace.

Features
- Login (OAuth2 password flow) to obtain a bearer token from `/token`.
- Send prompts to `/prompt` and display response preview, tokens used and estimated cost.

Quick start

1. Install Python dependencies (preferably in a virtualenv):

```bash
python -m pip install -r requirements.txt
```

2. Run the backend FastAPI app (example):

```bash
# From this repo root; the project exposes FastAPI app in main.py
uvicorn main:app --reload
```

3. Run the Streamlit frontend:

```bash
streamlit run streamlit_app.py
```

4. In the sidebar set the backend URL (default http://localhost:8000), login with seeded users (admin/admin123 or user/user123), then send prompts.

Notes
- The app uses the backend `/prompt` endpoint and expects the backend to return a JSON with `llm_response`, `tokens_used`, and `cost_usd` fields. If your backend returns different keys, adjust `streamlit_app.py` accordingly.
