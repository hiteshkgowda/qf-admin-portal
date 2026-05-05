# Qatar Foundation Admin Portal

Admin portal for managing the Universal Skills Passport — a credential tracking system that lets Qatar Foundation administrators oversee opportunities, learners, verifiers, and collaborators.

---

## What's inside

- **Auth** — sign up, log in, forgot/reset password, remember-me sessions
- **Opportunity Management** — create, edit, delete opportunities with skills, categories, and applicant limits
- **Dashboard** — at-a-glance stats, charts, and recent activity
- **Dark mode** — persisted via a toggle in the top bar

---

## Running locally

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:8080
```

No API keys needed. The database (`portal.db`) is created automatically on first run.

---

## Deploying to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)

The `render.yaml` is already configured. Just connect the repo and set `SECRET_KEY` to a random string in Render's environment variables.

---

## Project structure

```
app.py          Flask backend — auth + opportunity CRUD
sky/
  admin.html    Single-page frontend
  admin.css     Qatar Foundation green theme + dark mode
  admin.js      Form handling, dashboard interactions
portal.db       SQLite database (auto-created)
```
