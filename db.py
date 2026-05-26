from pathlib import Path

import mysql.connector

from config import Config

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
config = Config()


def get_connection(*, database=None):
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=database or config.MYSQL_DATABASE,
    )


def get_db():
    from flask import g

    if "db" not in g:
        g.db = get_connection()
    return g.db


def close_db(_error=None):
    from flask import g

    db = g.pop("db", None)
    if db is not None and db.is_connected():
        db.close()


def _split_sql_statements(script):
    statements = []
    current = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
    remainder = "\n".join(current).strip()
    if remainder:
        statements.append(remainder)
    return statements


def _run_schema_script(connection, script):
    cursor = connection.cursor()
    for statement in _split_sql_statements(script):
        cursor.execute(statement)
    connection.commit()
    cursor.close()


def init_db():
    server = mysql.connector.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
    )
    cursor = server.cursor()
    cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{config.MYSQL_DATABASE}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    server.commit()
    cursor.close()
    server.close()

    db = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
        _run_schema_script(db, schema_file.read())
    ensure_migrations(db)
    ensure_default_admin(db)
    db.close()


def table_has_column(db, table, column):
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (config.MYSQL_DATABASE, table, column),
    )
    row = cursor.fetchone()
    cursor.close()
    return bool(row and row[0])


def ensure_migrations(db):
    if not table_has_column(db, "exams", "duration_minutes"):
        db.cursor().execute(
            "ALTER TABLE exams ADD COLUMN duration_minutes INT NOT NULL DEFAULT 30"
        )
        db.commit()

    if not table_has_column(db, "attempts", "student_id"):
        db.cursor().execute("ALTER TABLE attempts ADD COLUMN student_id INT NULL")
        db.commit()

    if not table_has_column(db, "users", "auth0_sub"):
        db.cursor().execute(
            "ALTER TABLE users ADD COLUMN auth0_sub VARCHAR(255) NULL UNIQUE AFTER role"
        )
        db.commit()

    cursor = db.cursor()
    cursor.execute("SHOW TABLES LIKE 'users'")
    if not cursor.fetchone():
        cursor.execute(
            """
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                username VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NULL,
                role ENUM('admin', 'student') NOT NULL,
                auth0_sub VARCHAR(255) NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.commit()
    cursor.close()


def ensure_default_admin(db):
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if cursor.fetchone():
        cursor.close()
        return
    cursor.close()

    from werkzeug.security import generate_password_hash

    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO users (full_name, username, password_hash, role)
        VALUES (%s, %s, %s, 'admin')
        """,
        ("System Admin", "admin", generate_password_hash("admin123")),
    )
    db.commit()
    cursor.close()


def fetch_one(db, query, params=()):
    cursor = db.cursor(dictionary=True)
    cursor.execute(query, params)
    row = cursor.fetchone()
    cursor.close()
    return row


def fetch_all(db, query, params=()):
    cursor = db.cursor(dictionary=True)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows
