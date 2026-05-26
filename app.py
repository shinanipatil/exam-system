import csv
import io
import random
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from db import close_db, fetch_all, fetch_one, get_db, init_db

config = Config()

app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY

app.teardown_appcontext(close_db)

oauth = OAuth(app)
if config.auth0_enabled:
    oauth.register(
        "auth0",
        client_id=config.AUTH0_CLIENT_ID,
        client_secret=config.AUTH0_CLIENT_SECRET,
        client_kwargs={"scope": "openid profile email"},
        server_metadata_url=f"https://{config.AUTH0_DOMAIN}/.well-known/openid-configuration",
    )


def get_or_create_auth0_user(userinfo):
    sub = userinfo.get("sub")
    email = (userinfo.get("email") or "").strip().lower()
    name = (userinfo.get("name") or userinfo.get("nickname") or email.split("@")[0] or "Student").strip()
    if not sub:
        return None

    db = get_db()
    user = fetch_one(db, "SELECT * FROM users WHERE auth0_sub = %s", (sub,))
    if user:
        return user

    username = email or f"user_{sub.replace('|', '_')[:200]}"
    existing = fetch_one(db, "SELECT id FROM users WHERE username = %s", (username,))
    if existing:
        username = f"{username}_{sub[-8:]}"

    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO users (full_name, username, password_hash, role, auth0_sub)
        VALUES (%s, %s, NULL, 'student', %s)
        """,
        (name, username, sub),
    )
    db.commit()
    user_id = cursor.lastrowid
    cursor.close()
    return fetch_one(db, "SELECT * FROM users WHERE id = %s", (user_id,))


def login_user(user):
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return fetch_one(get_db(), "SELECT * FROM users WHERE id = %s", (user_id,))


@app.context_processor
def inject_user():
    return {"current_user": current_user(), "auth0_enabled": config.auth0_enabled}


def login_required(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please login to continue.", "error")
                return redirect(url_for("login"))
            if role and user["role"] != role:
                flash("You are not authorized for this page.", "error")
                return redirect(url_for("home"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def parse_exam_form():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    try:
        positive_marks = float(request.form.get("positive_marks", "1"))
        negative_marks = float(request.form.get("negative_marks", "0"))
        duration_minutes = int(request.form.get("duration_minutes", "30"))
        question_count = int(request.form.get("question_count", "1"))
    except ValueError:
        return None, "Please enter valid numeric values."

    if not title:
        return None, "Exam title is required."
    if positive_marks <= 0:
        return None, "Positive marks must be greater than 0."
    if negative_marks < 0:
        return None, "Negative marks cannot be negative."
    if question_count < 1 or question_count > 100:
        return None, "Question count must be between 1 and 100."
    if duration_minutes < 1 or duration_minutes > 300:
        return None, "Duration must be between 1 and 300 minutes."

    questions = []
    for i in range(1, question_count + 1):
        question_text = request.form.get(f"question_text_{i}", "").strip()
        option_a = request.form.get(f"option_a_{i}", "").strip()
        option_b = request.form.get(f"option_b_{i}", "").strip()
        option_c = request.form.get(f"option_c_{i}", "").strip()
        option_d = request.form.get(f"option_d_{i}", "").strip()
        correct_option = request.form.get(f"correct_option_{i}", "")
        if not all([question_text, option_a, option_b, option_c, option_d, correct_option]):
            return None, f"All fields are required for Question {i}."
        if correct_option not in {"A", "B", "C", "D"}:
            return None, f"Invalid correct option for Question {i}."
        questions.append((question_text, option_a, option_b, option_c, option_d, correct_option))

    return {
        "title": title,
        "description": description,
        "positive_marks": positive_marks,
        "negative_marks": negative_marks,
        "duration_minutes": duration_minutes,
        "question_count": question_count,
        "questions": questions,
    }, None


@app.route("/")
def home():
    db = get_db()
    exams = fetch_all(
        db,
        """
        SELECT e.*, COUNT(q.id) AS question_count
        FROM exams e
        LEFT JOIN questions q ON e.id = q.exam_id
        GROUP BY e.id
        ORDER BY e.created_at DESC
        """,
    )
    return render_template("index.html", exams=exams)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not full_name or not username or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))

        db = get_db()
        existing = fetch_one(db, "SELECT id FROM users WHERE username = %s", (username,))
        if existing:
            flash("Username already exists.", "error")
            return redirect(url_for("register"))

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO users (full_name, username, password_hash, role) VALUES (%s, %s, %s, 'student')",
            (full_name, username, generate_password_hash(password)),
        )
        db.commit()
        cursor.close()
        flash("Student account created. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = fetch_one(db, "SELECT * FROM users WHERE username = %s", (username,))
        if (
            not user
            or not user.get("password_hash")
            or not check_password_hash(user["password_hash"], password)
        ):
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))

        login_user(user)
        flash(f"Welcome {user['full_name']}.", "success")
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/login/google")
def login_google():
    if not config.auth0_enabled:
        flash(
            "Google sign-in is not configured. In .env, replace placeholder Auth0 values "
            "with your real Domain, Client ID, and Client Secret from manage.auth0.com.",
            "error",
        )
        return redirect(url_for("login"))
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("auth_callback", _external=True),
        connection="google-oauth2",
    )


@app.route("/callback")
def auth_callback():
    if not config.auth0_enabled:
        flash("Google sign-in is not configured.", "error")
        return redirect(url_for("login"))

    try:
        token = oauth.auth0.authorize_access_token()
    except Exception:
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("login"))

    userinfo = token.get("userinfo")
    if not userinfo:
        flash("Could not read your Google profile.", "error")
        return redirect(url_for("login"))

    user = get_or_create_auth0_user(userinfo)
    if not user:
        flash("Could not create your account.", "error")
        return redirect(url_for("login"))

    login_user(user)
    flash(f"Welcome {user['full_name']}.", "success")
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("home"))


@app.route("/create-exam", methods=["GET", "POST"])
@login_required(role="admin")
def create_exam():
    if request.method == "POST":
        parsed, error = parse_exam_form()
        if error:
            flash(error, "error")
            return redirect(url_for("create_exam"))

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO exams (title, description, positive_marks, negative_marks, duration_minutes)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                parsed["title"],
                parsed["description"],
                parsed["positive_marks"],
                parsed["negative_marks"],
                parsed["duration_minutes"],
            ),
        )
        exam_id = cursor.lastrowid

        for question in parsed["questions"]:
            cursor.execute(
                """
                INSERT INTO questions
                (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (exam_id, *question),
            )

        db.commit()
        cursor.close()
        flash("Exam created successfully.", "success")
        return redirect(url_for("home"))

    return render_template("create_exam.html")


@app.route("/take-exam/<int:exam_id>", methods=["GET", "POST"])
@login_required(role="student")
def take_exam(exam_id):
    db = get_db()
    exam = fetch_one(db, "SELECT * FROM exams WHERE id = %s", (exam_id,))
    if exam is None:
        flash("Exam not found.", "error")
        return redirect(url_for("home"))

    questions = fetch_all(db, "SELECT * FROM questions WHERE exam_id = %s", (exam_id,))
    if not questions:
        flash("This exam has no questions yet.", "error")
        return redirect(url_for("home"))

    question_map = {row["id"]: row for row in questions}
    submitted_order = request.form.get("question_order", "").strip()
    if submitted_order:
        question_ids = [int(item) for item in submitted_order.split(",") if item.isdigit()]
        question_ids = [qid for qid in question_ids if qid in question_map]
    else:
        question_ids = [row["id"] for row in questions]
        random.shuffle(question_ids)
    ordered = [question_map[qid] for qid in question_ids]

    if request.method == "POST":
        correct_count = 0
        wrong_count = 0

        for question in ordered:
            selected = request.form.get(f"answer_{question['id']}")
            if not selected:
                continue
            if selected == question["correct_option"]:
                correct_count += 1
            else:
                wrong_count += 1

        score = (correct_count * float(exam["positive_marks"])) - (
            wrong_count * float(exam["negative_marks"])
        )
        score = round(score, 2)

        user = current_user()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO attempts (exam_id, student_id, student_name, score, total_questions, correct_count, wrong_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (exam_id, user["id"], user["full_name"], score, len(ordered), correct_count, wrong_count),
        )
        attempt_id = cursor.lastrowid
        db.commit()
        cursor.close()

        return redirect(url_for("result", attempt_id=attempt_id))

    order_string = ",".join(str(qid) for qid in question_ids)
    return render_template("take_exam.html", exam=exam, questions=ordered, order_string=order_string)


@app.route("/result/<int:attempt_id>")
def result(attempt_id):
    db = get_db()
    attempt = fetch_one(
        db,
        """
        SELECT a.*, e.title AS exam_title, e.positive_marks, e.negative_marks
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        WHERE a.id = %s
        """,
        (attempt_id,),
    )

    if attempt is None:
        flash("Result not found.", "error")
        return redirect(url_for("home"))

    max_score = round(attempt["total_questions"] * float(attempt["positive_marks"]), 2)
    return render_template("result.html", attempt=attempt, max_score=max_score)


@app.route("/results")
@login_required()
def results():
    db = get_db()
    user = current_user()
    if user["role"] == "admin":
        attempts = fetch_all(
            db,
            """
            SELECT a.*, e.title AS exam_title
            FROM attempts a
            JOIN exams e ON e.id = a.exam_id
            ORDER BY a.attempted_at DESC
            """,
        )
    else:
        attempts = fetch_all(
            db,
            """
            SELECT a.*, e.title AS exam_title
            FROM attempts a
            JOIN exams e ON e.id = a.exam_id
            WHERE a.student_id = %s
            ORDER BY a.attempted_at DESC
            """,
            (user["id"],),
        )
    return render_template("results.html", attempts=attempts)


@app.route("/leaderboard/<int:exam_id>")
def leaderboard(exam_id):
    db = get_db()
    exam = fetch_one(db, "SELECT * FROM exams WHERE id = %s", (exam_id,))
    if exam is None:
        flash("Exam not found.", "error")
        return redirect(url_for("home"))
    rows = fetch_all(
        db,
        """
        SELECT student_name, MAX(score) AS best_score, MAX(correct_count) AS best_correct
        FROM attempts
        WHERE exam_id = %s
        GROUP BY student_name
        ORDER BY best_score DESC, best_correct DESC, student_name ASC
        """,
        (exam_id,),
    )
    return render_template("leaderboard.html", exam=exam, rows=rows)


@app.route("/admin/exams")
@login_required(role="admin")
def admin_exams():
    db = get_db()
    exams = fetch_all(
        db,
        """
        SELECT e.*, COUNT(q.id) AS question_count
        FROM exams e
        LEFT JOIN questions q ON e.id = q.exam_id
        GROUP BY e.id
        ORDER BY e.created_at DESC
        """,
    )
    return render_template("admin_exams.html", exams=exams)


@app.route("/admin/exam/<int:exam_id>/edit", methods=["GET", "POST"])
@login_required(role="admin")
def edit_exam(exam_id):
    db = get_db()
    exam = fetch_one(db, "SELECT * FROM exams WHERE id = %s", (exam_id,))
    if not exam:
        flash("Exam not found.", "error")
        return redirect(url_for("admin_exams"))

    questions = fetch_all(
        db, "SELECT * FROM questions WHERE exam_id = %s ORDER BY id ASC", (exam_id,)
    )
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        positive_marks = float(request.form.get("positive_marks", "1"))
        negative_marks = float(request.form.get("negative_marks", "0"))
        duration_minutes = int(request.form.get("duration_minutes", "30"))
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE exams
            SET title = %s, description = %s, positive_marks = %s, negative_marks = %s, duration_minutes = %s
            WHERE id = %s
            """,
            (title, description, positive_marks, negative_marks, duration_minutes, exam_id),
        )

        for q in questions:
            cursor.execute(
                """
                UPDATE questions
                SET question_text = %s, option_a = %s, option_b = %s, option_c = %s, option_d = %s, correct_option = %s
                WHERE id = %s
                """,
                (
                    request.form.get(f"question_text_{q['id']}", "").strip(),
                    request.form.get(f"option_a_{q['id']}", "").strip(),
                    request.form.get(f"option_b_{q['id']}", "").strip(),
                    request.form.get(f"option_c_{q['id']}", "").strip(),
                    request.form.get(f"option_d_{q['id']}", "").strip(),
                    request.form.get(f"correct_option_{q['id']}", ""),
                    q["id"],
                ),
            )

        db.commit()
        cursor.close()
        flash("Exam updated successfully.", "success")
        return redirect(url_for("admin_exams"))

    return render_template("edit_exam.html", exam=exam, questions=questions)


@app.route("/admin/exam/<int:exam_id>/delete", methods=["POST"])
@login_required(role="admin")
def delete_exam(exam_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM exams WHERE id = %s", (exam_id,))
    db.commit()
    cursor.close()
    flash("Exam deleted.", "success")
    return redirect(url_for("admin_exams"))


@app.route("/admin/question/<int:question_id>/delete", methods=["POST"])
@login_required(role="admin")
def delete_question(question_id):
    db = get_db()
    row = fetch_one(db, "SELECT exam_id FROM questions WHERE id = %s", (question_id,))
    if row:
        cursor = db.cursor()
        cursor.execute("DELETE FROM questions WHERE id = %s", (question_id,))
        db.commit()
        cursor.close()
        flash("Question deleted.", "success")
        return redirect(url_for("edit_exam", exam_id=row["exam_id"]))
    flash("Question not found.", "error")
    return redirect(url_for("admin_exams"))


@app.route("/export/results.csv")
@login_required(role="admin")
def export_results_csv():
    db = get_db()
    attempts = fetch_all(
        db,
        """
        SELECT a.id, a.student_name, e.title AS exam_title, a.score, a.correct_count, a.wrong_count,
               a.total_questions, a.attempted_at
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        ORDER BY a.attempted_at DESC
        """,
    )
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Attempt ID", "Student", "Exam", "Score", "Correct", "Wrong", "Total", "Attempted At"])
    for row in attempts:
        writer.writerow(
            [
                row["id"],
                row["student_name"],
                row["exam_title"],
                row["score"],
                row["correct_count"],
                row["wrong_count"],
                row["total_questions"],
                row["attempted_at"],
            ]
        )
    return Response(
        stream.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=exam_results.csv"},
    )


@app.route("/export/results.pdf")
@login_required(role="admin")
def export_results_pdf():
    db = get_db()
    attempts = fetch_all(
        db,
        """
        SELECT a.student_name, e.title AS exam_title, a.score, a.correct_count, a.wrong_count, a.attempted_at
        FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        ORDER BY a.attempted_at DESC
        """,
    )

    pdf_buffer = io.BytesIO()
    pdf = canvas.Canvas(pdf_buffer, pagesize=letter)
    width, height = letter
    y = height - 50
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Online Exam System - Results Report")
    y -= 30
    pdf.setFont("Helvetica", 10)
    for row in attempts:
        line = (
            f"{row['student_name']} | {row['exam_title']} | Score: {row['score']} "
            f"| C:{row['correct_count']} W:{row['wrong_count']} | {row['attempted_at']}"
        )
        pdf.drawString(40, y, line[:110])
        y -= 16
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica", 10)
    pdf.save()
    pdf_buffer.seek(0)
    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=exam_results.pdf"},
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
