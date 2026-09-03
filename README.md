# Programming Assistant

A web app for a research study on AI-assisted programming learning.
Participants register, answer a pre-survey, solve a programming question in
an in-browser code editor (with an AI coach that guides them through
Planning → Monitoring → Reflection instead of just handing over answers),
then answer a post-survey.

**Stack at a glance:**
- **Backend:** Flask + MongoDB, JWT auth, OpenAI for the AI coach, real
  code execution (Python via `python3`, C++ compiled with `g++`)
- **Frontend:** Vue 3 + Vuetify, CodeMirror-based code editor

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, modify it, no permission needed.

---

## Quick start

You'll need Python 3.10+, Node.js, `g++`, and a MongoDB connection string
(a free [Atlas](https://www.mongodb.com/cloud/atlas) cluster works fine).

```bash
# 1. Backend
cd src
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill it in -- see "Environment variables" below
python -c "from app import app; app.run(debug=True, port=3001)"

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run serve
```

Open **http://localhost:8080/al-2025** and register an account. That's it —
you're running the full app locally.

---

## Project layout

```
src/        Flask backend
  app.py          all routes + AI-coach prompt logic
  form.py         WTForms classes
  requirements.txt
  Dockerfile      for deploying (see "Deploying" below)
  .env.example    template for your own .env (never commit the real one)
frontend/   Vue 3 frontend
  src/components/CodeEditorPage.vue   the main code editor + AI chat page
docs/       (currently empty)
tests/      (currently empty)
```

## Environment variables (`src/.env`)

Copy `src/.env.example` to `src/.env` and fill in real values. `.env` is
gitignored — **never commit it**, and never paste real secrets into a
commit message either.

| Variable | Required | Notes |
|---|---|---|
| `OPENAI_API_KEY` | Yes | From [platform.openai.com](https://platform.openai.com/api-keys). The AI coach and the safety-moderation check both use this. |
| `OPENAI_MODEL` | No | Defaults to `gpt-4o-mini` |
| `FLASK_SECRET_KEY` | Yes | Any random string. Generate one: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `MONGO_URI` | Yes | Your MongoDB connection string |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | Yes | An SMTP account for password-reset emails. For Gmail, use an [App Password](https://myaccount.google.com/apppasswords), not your real password. |
| `ALLOWED_ORIGINS` | No | Comma-separated frontend URLs allowed to call the API. Defaults to `http://localhost:8080`. If you run the frontend on a different port, add it here or API calls will be silently blocked by CORS. |

## How the AI coach works

The coach never writes solution code — it's enforced two ways: the system
prompt tells it not to, *and* a server-side check
(`response_contains_code()` in `app.py`) scans every reply and forces a
retry (or a fixed refusal) if code leaks through anyway. It also runs every
incoming student message through OpenAI's moderation endpoint before
responding.

It tracks a Planning → Monitoring → Debugging → Reflection cycle per
student per question (see `build_natural_srl_prompt()`), using real signals
— whether tests passed, whether there's a compiler error, how long they've
been at it — to decide what phase to coach for next.

## Adding a programming question

Insert a document into the `programmingQuestions` collection:

```js
{
  question_id: "programming_q3",       // must match this pattern
  question_text: "...",
  language: "python",                  // default/fallback language
  file_structure: { type: "single-file" },
  starter_code_by_language: {          // optional: offer a language picker
    python: "def main():\n    ...",
    cpp: "#include <iostream>\n..."
  },
  languages: ["python", "cpp"],        // optional: omit for single-language
  test_cases: [
    { test_name: "...", input: "...", expected_output: "..." }
  ]
}
```

Keep `input`/`expected_output` plain text with no language-specific setup —
that's what lets the same test cases work against either language. A
question can also be `file_structure.type: "multi-file"` (header + source
files) instead, but that mode is C++-only.

## Troubleshooting

- **"Failed to fetch" / CORS errors in the browser console** — the
  frontend's origin isn't in the backend's `ALLOWED_ORIGINS`. Add it to
  `src/.env` and restart the backend.
- **C++ questions fail to run/compile** — `g++` isn't on your PATH. macOS:
  install Xcode Command Line Tools (`xcode-select --install`). Debian/Ubuntu:
  `apt install build-essential`.
- **MongoDB connection errors** — check Atlas's *Network Access* allows
  your current IP (or `0.0.0.0/0` for local dev), and that the database
  user's password in `MONGO_URI` is correct and URL-safe.
- **AI coach errors** — check `OPENAI_API_KEY` is set and has quota. Set a
  spending limit on your OpenAI account (Settings → Billing → Limits)
  before letting anyone else use a deployed instance.

## Deploying

- **Backend** needs `g++` at runtime, so it deploys as a container — see
  `src/Dockerfile` (Python slim image + `build-essential`). Any host that
  runs Docker images works (Render, Fly.io, Railway, a VPS). Set the
  environment variables from the table above in that host's dashboard —
  never in the repo.
- **Frontend** builds to static files: `npm run build` → `frontend/dist/`.
  Serve that with any static host, setting `VUE_APP_API_BASE_URL` at build
  time to your deployed backend's URL (e.g.
  `https://your-backend.example.com/api/`).
- Once both are deployed, add the frontend's URL to the backend's
  `ALLOWED_ORIGINS`, or every API call will be blocked by CORS.
- In MongoDB Atlas, add your backend host's IP to *Network Access* (most
  PaaS hosts have dynamic IPs, so `0.0.0.0/0` is common in practice —
  database-user credentials are still required either way).

## Database collections

All created lazily on first use.

| Collection | What it holds |
|---|---|
| `users` | Accounts, `research_group` (`control`/`experiment`), completion status |
| `preSurveyQuestion` / `postSurveyQuestion` | Survey questions you seed yourself — each question needs a unique `index` |
| `preSurveyAnswers` / `postSurveyAnswers` | Submitted survey responses |
| `programmingQuestions` | The coding problems — see "Adding a programming question" above |
| `submissions`, `run_attempts`, `code_autosaves` | Per-question code history |
| `conversations`, `srl_conversation_states` | AI coach chat history and per-student SRL phase state |
| `ai_interactions` | Logged prompt/response pairs, for research analysis |
| `user_feedback` | Thumbs up/down on individual AI coach replies |
| `guardrail_violations` | Logged whenever the AI's reply leaked code and had to be caught/retried — useful as a research metric on its own |
| `moderation_flags` | Logged whenever a student message was flagged by OpenAI's moderation check |
| `user_activities`, `login_logs` | Usage/timing tracking for the study |
