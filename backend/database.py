import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL DEFAULT 'Новый чат',
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            sender      TEXT NOT NULL CHECK(sender IN ('user', 'bot')),
            text        TEXT NOT NULL,
            intent      TEXT,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        );
    """)

    conn.commit()
    conn.close()
    print(f"[DB] База данных инициализирована: {DB_PATH}")

def create_session(title="Новый чат"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_sessions (title) VALUES (?)",
        (title,)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def add_message(session_id, sender, text, intent=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (session_id, sender, text, intent) VALUES (?, ?, ?, ?)",
        (session_id, sender, text, intent)
    )
    message_id = cursor.lastrowid

    cursor.execute(
        "UPDATE chat_sessions SET updated_at = datetime('now', 'localtime') WHERE id = ?",
        (session_id,)
    )

    conn.commit()
    conn.close()
    return message_id

def update_session_title(session_id, title):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE chat_sessions SET title = ? WHERE id = ?",
        (title, session_id)
    )
    conn.commit()
    conn.close()

def get_all_sessions():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            s.id,
            s.title,
            s.created_at,
            s.updated_at,
            COUNT(m.id) as message_count
        FROM chat_sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        GROUP BY s.id
        ORDER BY s.updated_at DESC
    """)
    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sessions

def get_session_messages(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, sender, text, intent, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    )
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return messages

def delete_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def get_command_frequencies():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT text, COUNT(*) as count
        FROM messages
        WHERE sender = 'user'
        GROUP BY LOWER(text)
        ORDER BY count DESC
        LIMIT 100
    """)
    results = [{"word": row["text"], "count": row["count"]} for row in cursor.fetchall()]
    conn.close()
    return results
