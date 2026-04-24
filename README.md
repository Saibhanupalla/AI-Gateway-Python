# AI Gateway — Enterprise Edition

An enterprise-ready AI Gateway that provides a unified API to multiple LLM providers (OpenAI, Anthropic, Google) with full observability, governance, and control.

## Features
- **Multi-Provider Routing:** Fallback chains and retries across OpenAI, Anthropic, and Google Models.
- **Data Privacy:** On-the-fly PII redaction using Microsoft Presidio (masks names, emails, credit cards, etc. before hitting the LLMs).
- **Cost & Token Tracking:** Centralized counting of cost and token usage.
- **Rate Limiting:** Granular budgets (per user, per department, and global).
- **Caching:** Exact-match caching to save compute on identical requests.
- **Guardrails:** Pre- and post-request content filtering, max length checks, JSON validation, and regex blacklisting.
- **API Key Management:** Secure (encrypted) virtual key management for LLM providers.
- **React Dashboard:** A premium Next.js local dashboard for admin control and playground testing.

## Tech Stack
- **Backend:** Python + FastAPI + SQLModel (SQLite default, easy Postgres migration).
- **Frontend:** Next.js + React + Recharts + Vanilla CSS Design System.

## How to Run

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   npm install --prefix dashboard
   ```

2. **Configure Environment**
   Update your `.env` with your API keys:
   ```env
   OPENAI_API_KEY="sk-..."
   ANTHROPIC_API_KEY="sk-ant-..."
   GOOGLE_API_KEY="AIza..."
   JWT_SECRET_KEY="some-secure-random-string"
   ENCRYPTION_KEY="<generate using fernet>"
   ```

3. **Start the Backend**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

4. **Start the Frontend Dashboard**
   ```bash
   cd dashboard
   npm run dev
   ```

5. **Login**
   - Access the dashboard at `http://localhost:3000`
   - Default login: `username: admin`, `password: admin123`

## Testing via the Dashboard
Once logged in, open the **Playground** tab from the sidebar. You can type prompts, force PII (e.g., "My email is test@example.com"), and see the redacted output along with the LLM's response, token count, cost, and latency.

