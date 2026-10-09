# TaskMind — AI Productivity Demo

TaskMind is a Streamlit task-management portfolio demo with a deterministic daily
planner, project and milestone tracking, a calendar, analytics, and optional Groq
AI workflows. Regular task CRUD and planning work without an AI key.

## Run locally

Requires Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
# Optional: DATABASE_URL=sqlite:///todos.db
# Optional: GROQ_MODEL=openai/gpt-oss-20b
```

Start the app:

```powershell
streamlit run app.py
```

On first startup, the app creates its additional tables and adds missing task
columns to the existing SQLite database without deleting task records. SQLite
is the local fallback. Set `DATABASE_URL` to a SQLAlchemy-compatible database
URL to use another database.

## Deploy on Streamlit Community Cloud

1. Push the project to GitHub. `.gitignore` excludes `.env`, local databases, and
   virtual environments; do not commit credentials or real task data.
2. In Streamlit Community Cloud, create an app from the repository, select the
   `main` branch, and set the entry point to `app.py`.
3. In the app's **Settings → Secrets**, add:

   ```toml
   GROQ_API_KEY = "your_groq_api_key"
   ```

4. Deploy and use the generated public URL.

The default deployment is intentionally a shared, unauthenticated demo. All
visitors can see and change the same tasks and settings. Do not enter personal
or confidential information. Community Cloud's local filesystem is not a
durable database; SQLite data may be lost when the app restarts or is rebuilt.
For private, persistent multi-user data, add authentication and user-level
authorization and connect a managed PostgreSQL database before collecting any
real user data.

## Features

- Dashboard metrics, due-soon tasks, priorities, and an optional AI briefing.
- Task CRUD, status and priority filters, search, bulk status updates, and a
  Kanban-style status view.
- Optional structured AI task drafts that are reviewed before saving.
- A deterministic planner with priority/deadline ranking, accepted-block
  conflict checks, a lunch break, buffers, and a daily workload limit.
- Projects, milestones, monthly deadline calendar, manual schedule blocks, and
  database-backed analytics.
- Groq-powered task assistant; normal CRUD continues to work without Groq.

## Tests

Install the development dependency and run the focused tests:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```
