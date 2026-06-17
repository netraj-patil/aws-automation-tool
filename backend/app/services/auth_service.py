"""SQLite-backed local authentication and JWT generation."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from uuid import uuid4


class EmailAlreadyRegisteredError(Exception):
    """Raised when an account already exists for an email address."""


class InvalidCredentialsError(Exception):
    """Raised when login credentials do not match a stored account."""


class AuthService:
    """Persist users, hash passwords, and issue signed access tokens."""

    _HASH_ITERATIONS = 600_000

    def __init__(
        self,
        database_path: str | Path | None = None,
        jwt_secret: str | None = None,
    ) -> None:
        default_path = Path(__file__).resolve().parents[2] / "data" / "auth.db"
        self.database_path = Path(
            database_path or os.getenv("AUTH_DB_PATH", default_path)
        )
        self.jwt_secret = (
            jwt_secret
            or os.getenv("JWT_SECRET")
            or "development-only-change-me"
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self._HASH_ITERATIONS,
        )
        return (
            f"pbkdf2_sha256${self._HASH_ITERATIONS}$"
            f"{self._encode(salt)}${self._encode(digest)}"
        )

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations, salt, expected = stored_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                self._decode(salt),
                int(iterations),
            )
            return hmac.compare_digest(digest, self._decode(expected))
        except (TypeError, ValueError):
            return False

    def _create_token(self, user_id: str, email: str) -> str:
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": user_id,
            "email": email,
            "iat": now,
            "exp": now + 24 * 60 * 60,
        }
        segments = [
            self._encode(
                json.dumps(header, separators=(",", ":")).encode("utf-8")
            ),
            self._encode(
                json.dumps(payload, separators=(",", ":")).encode("utf-8")
            ),
        ]
        signing_input = ".".join(segments).encode("ascii")
        signature = hmac.new(
            self.jwt_secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        return f"{'.'.join(segments)}.{self._encode(signature)}"

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict[str, str]:
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "email": str(row["email"]),
        }

    def register(
        self, name: str, email: str, password: str
    ) -> tuple[str, dict[str, str]]:
        user_id = str(uuid4())
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users (id, name, email, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        name.strip(),
                        email.strip().lower(),
                        self._hash_password(password),
                        int(time.time()),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise EmailAlreadyRegisteredError from exc

        user = {"id": user_id, "name": name.strip(), "email": email.lower()}
        return self._create_token(user_id, user["email"]), user

    def login(
        self, email: str, password: str
    ) -> tuple[str, dict[str, str]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()

        if row is None or not self._verify_password(
            password, str(row["password_hash"])
        ):
            raise InvalidCredentialsError

        user = self._public_user(row)
        return self._create_token(user["id"], user["email"]), user


auth_service = AuthService()
