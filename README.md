# Online Exam System

A full-stack Online Exam System using:
- Frontend: HTML, CSS, JavaScript
- Backend: Python (Flask)
- Database: MySQL
- Authentication: Auth0 (Continue with Google) + local username/password

## Features
- Create MCQ exams with custom question count.
- Configure positive and negative marking.
- Admin login and student login/registration.
- **Continue with Google** for students (via Auth0).
- Let students take exams online.
- Exam timer with auto-submit when time ends.
- Randomized question order for each attempt.
- Auto-calculate scores from correct and wrong answers.
- View individual result pages and attempt history.
- Leaderboard/rank list per exam.
- Admin can edit/delete exams and questions.
- Export results as CSV and PDF.

## Project Structure
- `app.py` - Flask backend, routes, Auth0
- `config.py` - Environment configuration
- `db.py` - MySQL connection and schema setup
- `schema.sql` - MySQL schema
- `templates/` - HTML pages
- `static/` - CSS and JavaScript
- `.env` - Local secrets (copy from `.env.example`)

## Prerequisites
1. **MySQL** installed and running (e.g. MySQL 8 or MariaDB).
2. **Auth0 account** (free tier) for Google sign-in.

## Setup

### 1. MySQL
Create a user/password if needed, then copy environment file:

```powershell
copy .env.example .env
```

Edit `.env` and set `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE`.

The app creates the database and tables automatically on first run.

### 2. Auth0 + Google

1. Sign in at [Auth0 Dashboard](https://manage.auth0.com).
2. Create an **Application** → type **Regular Web Application**.
3. In **Settings**, set:
   - **Allowed Callback URLs**: `http://127.0.0.1:5000/callback`
   - **Allowed Logout URLs**: `http://127.0.0.1:5000`
   - **Allowed Web Origins**: `http://127.0.0.1:5000`
4. Copy **Domain**, **Client ID**, and **Client Secret** into `.env` as `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`.
5. Go to **Authentication → Social** and enable **Google** (or add Google in **Connections** for this app).

Students use **Continue with Google** on the login page. They are stored as `student` role in MySQL.

### 3. Run locally (Windows)

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py -3 app.py
```

Open: http://127.0.0.1:5000

## Default accounts
- **Admin** (username/password): `admin` / `admin123`
- **Students**: register locally, or sign in with Google when Auth0 is configured

## Notes
- Google users have no local password; they must use **Continue with Google**.
- If Auth0 variables are missing, the Google button is hidden; username login still works.
- Marking: Score = (`correct_count` × positive_marks) − (`wrong_count` × negative_marks)
