# Smart Planner

An AI-assisted productivity web app built with Django.

Smart Planner helps users create and execute tasks based on current energy/mood, manage recurring and team tasks, generate study plans with AI, and track progress through XP, levels, and badges.

## Highlights

- AI task creation with automatic:
  - category classification
  - difficulty estimation
  - time estimate
  - actionable subtasks
- Mood-based task activation (Easy/Moderate/Hard energy mapping)
- Personal and team task workflows
- Kanban board for INBOX / ACTIVE / COMPLETED states
- Pomodoro-style task timer with start/pause/add-time/edit
- Recurring tasks (daily/weekly auto-reset after completion)
- AI-powered study plan generation (1 to 90 days)
- Day-wise extraction of study plan tasks into dashboard tasks
- OTP-based signup verification and password reset
- Profile analytics, XP levels, and badge unlocking
- Render-ready deployment config with Gunicorn + WhiteNoise

## Tech Stack

- Backend: Django 5
- Database: SQLite locally (or any `DATABASE_URL`-compatible DB in production)
- AI: Groq API (`llama-3.1-8b-instant`)
- Email: Brevo API (preferred) with SMTP fallback
- Background jobs: `django-background-tasks`
- Static serving in production: WhiteNoise
- WSGI server: Gunicorn

## Project Structure

```text
.
|-- antiprocastination/       # Django project settings, root URLs, WSGI/ASGI
|-- core/                     # Main app (models, views, URLs, templates, AI service)
|-- core/templates/core/      # Main app templates
|-- core/templates/registration/
|-- manage.py
|-- requirements.txt
|-- render.yaml               # Render deployment config
|-- env.example               # Required environment variables
```

## Core Features

### 1. Task Management

- Create tasks manually or with AI.
- Task states:
  - `INBOX`
  - `ACTIVE`
  - `COMPLETED`
  - `DELETED`
- Priority levels:
  - `1` Low
  - `2` Medium
  - `3` High
- Optional scheduling date and deadlines.
- Snooze support.

### 2. Mood-to-Task Engine

Users choose current energy level and Smart Planner activates the best matching task by difficulty and priority order.

### 3. Task Timer

Each active task supports a timer with endpoints for:

- start
- pause
- add 5 minutes
- edit duration
- fetch current status

### 4. Recurring Tasks

Recurring tasks (`DAILY` / `WEEKLY`) are automatically reset back to `INBOX` on completion and moved to the next cycle date.

### 5. Team Collaboration

- Create teams
- Invite members
- Assign tasks to one member or all members
- Member-side scheduling for assigned tasks
- Team dashboard for active/inbox/completed visibility

### 6. Study Plan System

- Generate AI study plans by subject, goal, and duration.
- Plan parser extracts `## Day N: Title` blocks.
- Add selected day tasks from a plan directly to dashboard.
- Track and complete/delete plans.

### 7. Authentication and Recovery

- OTP-based signup flow
- OTP resend flow
- Forgot-password OTP verification and password reset
- Strong password checks
- Local development fallback message if email delivery fails

### 8. Gamification and Analytics

- XP and level progression
- Badge system based on completion behavior
- Productivity slot analytics (time-of-day work patterns)

## Data Model Overview

Main models in `core/models.py`:

- `Todo`
- `Profile`
- `Badge`
- `UserBadge`
- `Team`
- `StudyPlan`
- `OTPVerification`

## Environment Variables

Create a `.env` file in project root.

You can start from `env.example`:

```env
GROQ_API_KEY=your_groq_api_key
BREVO_API_KEY=your_brevo_api_key
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=
EMAIL_TIMEOUT=15
SECRET_KEY=your_django_secret_key
DATABASE_URL=any_sql_database
```

### Important Notes

- `BREVO_API_KEY` is preferred for OTP delivery in hosted environments.
- If `BREVO_API_KEY` is missing, code falls back to SMTP credentials.
- `EMAIL_TIMEOUT` is important to prevent SMTP hangs under Gunicorn.

## Local Setup

### 1. Clone and enter project

```bash
git clone <your-repo-url>
cd smart-planner
```

### 2. Create and activate virtual environment

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp env.example .env
```

Then update values in `.env`.

### 5. Apply migrations

```bash
python manage.py migrate
```

### 6. Create admin user (optional)

```bash
python manage.py createsuperuser
```

### 7. Run server

```bash
python manage.py runserver
```

Open: `http://127.0.0.1:8000/`

## URL Map (Core)

Root routes:

- `/` dashboard
- `/accounts/` Django auth routes (login/logout/password)
- `/admin/` admin

Key app routes include:

- `/createtodo_ai/`
- `/add_manual/`
- `/complete/<task_id>/`
- `/delete/<task_id>/`
- `/snooze/<task_id>/`
- `/task/start/<task_id>/`
- `/task/add_time/<task_id>/`
- `/task/pause/<task_id>/`
- `/task/edit_time/<task_id>/`
- `/task/status/<task_id>/`
- `/kanban/`
- `/history/`
- `/teams/` and nested team routes
- `/study-plan/...` routes
- `/profile/`
- `/signup/`, `/verify-otp/`, `/resend-otp/`
- `/forgot-password/`, `/forgot-password/verify/`

## Deployment (Render)

`render.yaml` is already configured for web deployment.

Build command:

```bash
pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate
```

Start command:

```bash
gunicorn antiprocastination.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

Set all required environment variables in Render dashboard.

## Running Tests

```bash
python manage.py test
```

Current tests in `core/tests.py` cover:

- signup pending-user reuse behavior
- OTP activation flow
- study plan view handling edge case day titles

## Security and Content Guardrails

- Blocks unsafe topic patterns before AI task/plan generation.
- Profanity filtering on signup username.
- Strong password policy enforcement.
- OTP validity limited to 5 minutes.

## Known Gaps / Future Improvements

- Add API layer (DRF) for mobile or SPA clients
- Increase test coverage for team + recurring + timer flows
- Improve background reminder scheduling setup/documentation
- Add role permissions for team managers beyond owner/member
- Add production-grade observability/log aggregation

## License

No license file is currently included in this repository. Add one (e.g., MIT) if this project will be publicly distributed.
