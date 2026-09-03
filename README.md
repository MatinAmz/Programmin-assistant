# Programming Assistant

A web app for a research study on AI-assisted programming learning. Participants
register, complete a pre-survey, solve programming questions in an in-browser
code editor (with an AI assistant — either free-form "control" mode or
self-regulated-learning "experiment" mode, assigned at random), then complete a
post-survey.

- **Backend:** Flask, MongoDB (via Atlas), JWT auth, OpenAI API for the AI
  assistant, real C++ compilation via `g++` for programming submissions
- **Frontend:** Vue 3 + Vuetify, CodeMirror/Monaco code editor

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, modify it, no permission needed.

## Project layout

```
src/        Flask backend (app.py, form.py, templates/, static/)
frontend/   Vue 3 frontend
docs/       (currently empty)
tests/      (currently empty)
```

## Running it locally

### Prerequisites

- Python 3.10+
- Node.js + npm
- A MongoDB database (a free [Atlas](https://www.mongodb.com/cloud/atlas)
  cluster works, or a local `mongod`)
- An [OpenAI API key](https://platform.openai.com/api-keys)
- A C++ compiler (`g++`) on your PATH — needed for the programming-question
  code runner. Comes with Xcode Command Line Tools on macOS, `build-essential`
  on Debian/Ubuntu.

### Backend

```bash
cd src
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then fill in real values, see below
python -c "from app import app; app.run(debug=True, port=3001)"
```

### Frontend

```bash
cd frontend
npm install
npm run serve
```

Open **http://localhost:8080/al-2025**.

### Environment variables (`src/.env`)

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `OPENAI_MODEL` | Defaults to `gpt-4o-mini` if unset |
| `FLASK_SECRET_KEY` | Any random string — used to sign sessions/tokens. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `MONGO_URI` | Your MongoDB connection string |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | An SMTP account (Gmail App Password works) for password-reset emails |
| `ALLOWED_ORIGINS` | Comma-separated list of frontend origins allowed to call the API. Defaults to `http://localhost:8080` |

`.env` is gitignored — never commit real secrets. `src/.env.example` is the
template.

## Deploying

- **Backend:** needs a C++ toolchain available at runtime, so it's set up to
  deploy as a container — see `src/Dockerfile`. Any host that runs
  Docker images (Render, Fly.io, Railway, a VPS, etc.) works; point its start
  command at the same `gunicorn app:app` the Dockerfile uses, and set the
  environment variables above in that host's dashboard (never in the repo).
- **Frontend:** a static build (`npm run build` → `frontend/dist/`) served by
  any static host. Set `VUE_APP_API_BASE_URL` at build time to your deployed
  backend's URL (e.g. `https://your-backend.example.com/api/`).
- Update the backend's `ALLOWED_ORIGINS` to include your deployed frontend's
  URL once you have one, or API calls will be blocked by CORS.

## Database

MongoDB collections used (all created lazily on first use, except where noted):

- `users` — registered accounts, `research_group` (`control`/`experiment`),
  completion status
- `preSurveyQuestion` / `postSurveyQuestion` — survey questions (seed these
  yourself; each question needs a unique `index`)
- `preSurveyAnswers` / `postSurveyAnswers` — submitted survey responses
- `programmingQuestions` — the coding problems (see `question_id`,
  `question_text`, `language`, `test_cases`)
- `submissions`, `run_attempts`, `code_autosaves` — per-question code history
- `conversations`, `ai_interactions` — AI assistant chat history/logging
- `user_activities`, `login_logs` — usage/timing tracking for the study
