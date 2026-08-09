import base64
import hashlib
import hmac
import secrets


PBKDF2_ITERATIONS = 310_000
SALT_BYTES = 32


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError(
            "Password must contain at least 10 characters."
        )

    salt = secrets.token_bytes(SALT_BYTES)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )

    encoded_salt = base64.urlsafe_b64encode(
        salt
    ).decode("ascii")

    encoded_digest = base64.urlsafe_b64encode(
        digest
    ).decode("ascii")

    return (
        f"pbkdf2_sha256"
        f"${PBKDF2_ITERATIONS}"
        f"${encoded_salt}"
        f"${encoded_digest}"
    )


def verify_password(
    password: str,
    stored_hash: str,
) -> bool:
    try:
        algorithm, iterations, encoded_salt, expected_digest = (
            stored_hash.split("$", 3)
        )

        if algorithm != "pbkdf2_sha256":
            return False

        salt = base64.urlsafe_b64decode(
            encoded_salt.encode("ascii")
        )

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )

        encoded_digest = base64.urlsafe_b64encode(
            digest
        ).decode("ascii")

        return hmac.compare_digest(
            encoded_digest,
            expected_digest,
        )

    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
    ):
        return False


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
