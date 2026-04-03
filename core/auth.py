"""
auth.py — Système d'authentification léger pour le générateur de quizz.

Rôles : admin, formateur, utilisateur.
Stockage SQLite, hash via hashlib pbkdf2_hmac.
"""

import hashlib
import os
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

DB_PATH = os.getenv("QUIZ_SESSIONS_DB", "shared_data/quiz_sessions.db")


@dataclass
class User:
    user_id: str
    username: str
    display_name: str
    role: str  # "admin" | "formateur" | "utilisateur"
    created_at: str


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_users_table():
    """Crée la table users si elle n'existe pas et seed le compte admin."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'utilisateur',
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

    # Seed admin account if not exists
    cursor = conn.execute("SELECT 1 FROM users WHERE username = ?", ("admin",))
    if cursor.fetchone() is None:
        admin_password = os.getenv("ADMIN_PASSWORD", "admin")
        _create_user_internal(conn, "admin", "Administrateur", "admin", admin_password)

    conn.close()


def _hash_password(password: str, salt: str) -> str:
    """Hash un mot de passe avec PBKDF2-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    ).hex()


def _create_user_internal(conn: sqlite3.Connection, username: str, display_name: str, role: str, password: str) -> User:
    """Crée un utilisateur dans la base (usage interne)."""
    user_id = str(uuid.uuid4())
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    created_at = datetime.now().isoformat()

    conn.execute(
        "INSERT INTO users (user_id, username, display_name, role, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, display_name, role, password_hash, salt, created_at),
    )
    conn.commit()
    return User(user_id=user_id, username=username, display_name=display_name, role=role, created_at=created_at)


def authenticate(username: str, password: str) -> Optional[User]:
    """Authentifie un utilisateur. Retourne User si succès, None sinon."""
    conn = _get_connection()
    cursor = conn.execute(
        "SELECT user_id, username, display_name, role, password_hash, salt, created_at FROM users WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    user_id, uname, display_name, role, stored_hash, salt, created_at = row
    computed_hash = _hash_password(password, salt)

    if computed_hash != stored_hash:
        return None

    return User(user_id=user_id, username=uname, display_name=display_name, role=role, created_at=created_at)


def create_user(username: str, display_name: str, role: str, password: str) -> Optional[User]:
    """Crée un nouvel utilisateur. Retourne None si le username existe déjà."""
    conn = _get_connection()
    try:
        user = _create_user_internal(conn, username, display_name, role, password)
        conn.close()
        return user
    except sqlite3.IntegrityError:
        conn.close()
        return None


def list_users() -> List[User]:
    """Liste tous les utilisateurs."""
    conn = _get_connection()
    cursor = conn.execute("SELECT user_id, username, display_name, role, created_at FROM users ORDER BY created_at")
    users = [User(*row) for row in cursor.fetchall()]
    conn.close()
    return users


def update_user_role(username: str, new_role: str) -> bool:
    """Met à jour le rôle d'un utilisateur."""
    if new_role not in ("admin", "formateur", "utilisateur"):
        return False
    conn = _get_connection()
    cursor = conn.execute("UPDATE users SET role = ? WHERE username = ?", (new_role, username))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def delete_user(username: str) -> bool:
    """Supprime un utilisateur (sauf admin)."""
    if username == "admin":
        return False
    conn = _get_connection()
    cursor = conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def change_password(username: str, new_password: str) -> bool:
    """Change le mot de passe d'un utilisateur."""
    conn = _get_connection()
    salt = secrets.token_hex(16)
    password_hash = _hash_password(new_password, salt)
    cursor = conn.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
        (password_hash, salt, username),
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


# Initialiser la table au chargement du module
init_users_table()
