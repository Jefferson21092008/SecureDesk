import re

COMMON_PASSWORDS = {
    "123456789012",
    "password123!",
    "qwerty123456!",
    "admin123456!",
    "letmein123456!",
}


def reject_unsafe_text(value: str, *, field_name: str, allow_newlines: bool = False) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")

    for char in normalized:
        codepoint = ord(char)
        if char == "\t" and allow_newlines:
            continue
        if char in {"\n", "\r"} and allow_newlines:
            continue
        if codepoint < 32 or codepoint == 127:
            raise ValueError(f"{field_name} contains unsupported control characters")

    return normalized


def validate_password_strength(password: str, *, email: str | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    if len(password) > 128:
        raise ValueError("Password must contain at most 128 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in password):
        raise ValueError("Password cannot contain control characters")

    requirements = (
        (r"[a-z]", "a lowercase letter"),
        (r"[A-Z]", "an uppercase letter"),
        (r"[0-9]", "a digit"),
        (r"[^A-Za-z0-9]", "a symbol"),
    )
    for pattern, description in requirements:
        if re.search(pattern, password) is None:
            raise ValueError(f"Password must contain {description}")

    lowered = password.casefold()
    if lowered in COMMON_PASSWORDS:
        raise ValueError("Password is too common")

    if email:
        local_part = email.split("@", 1)[0].casefold()
        if len(local_part) >= 4 and local_part in lowered:
            raise ValueError("Password must not contain the email identifier")

    return password
