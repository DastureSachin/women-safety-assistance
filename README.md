# Women Safety & Emergency Assistance

A Flask and SQLite college demonstration app with account registration, private emergency contacts, incident reports, browser geolocation, and practical safety tips.

## Requirements

- Python 3.10 or newer
- Dependencies in `requirements.txt`

## Setup and run (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python app.py
```

Open <http://127.0.0.1:5000>, create an account, and log in. The SQLite database is created as `women_safety.db` in the project directory. Existing `users` records are preserved; any legacy plain-text passwords are upgraded to Werkzeug hashes during database initialization.

## Deploy to Render

1. Push this project to a GitHub repository.
2. In Render, choose **New +** → **Blueprint**, connect the repository, and deploy the included `render.yaml`.
3. The Blueprint configures Gunicorn, generates a `SECRET_KEY`, enables secure session cookies, and stores SQLite data on a persistent disk mounted at `/var/data`.
4. The Blueprint uses a paid Starter web service because Render persistent disks require a paid service. Review the current price shown in your Render dashboard before confirming deployment.
5. When deployment completes, open the service URL, register, and log in.

The persistent disk preserves accounts, contacts, and reports across deploys. Keep it mounted at `/var/data`; the `DATABASE` setting points the app to the database file there. Do not remove the disk or change the mount path unless you have backed up the database. If you choose a free service instead, SQLite data on its filesystem is ephemeral and can be lost during redeploys or restarts.

For a manual Render web service, use build command `pip install -r requirements.txt` and start command `gunicorn app:app`. Set `SECRET_KEY` to a unique secret, `DATABASE` to a path on a persistent disk, and `SESSION_COOKIE_SECURE` to `true`. Do not use Flask's development server for production.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The tests use a temporary SQLite database and do not alter the project database.

## Safety and privacy notes

- The SOS button is a local demonstration only. It does not call emergency services, message contacts, or confirm delivery.
- Location is requested only after an explicit browser action. Coordinates are shown in the page and are not transmitted to or stored by the application.
- Incident location is optional and is stored only when manually entered in the report form.
- The helpline numbers shown are examples for India; verify local numbers for your area.
