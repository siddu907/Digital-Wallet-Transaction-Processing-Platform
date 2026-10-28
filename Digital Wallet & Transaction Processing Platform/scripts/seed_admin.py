from sqlalchemy import func, select

from app.core.security import hash_password
from app.database import SessionLocal
from app.models import Role, User


def main() -> None:
    email = input("Super Admin email: ")
    name = input("Super Admin name: ")
    password = input("Super Admin password: ")
    email = email.strip().lower()
    name = name.strip()
    if not email or "@" not in email or not name or len(password) < 8:
        raise SystemExit("Enter a valid email, a name, and a password with at least 8 characters.")
    with SessionLocal.begin() as db:
        if db.scalar(select(func.count()).select_from(User)):
            raise SystemExit("Admin bootstrap is allowed only on an empty users table.")
        db.add(User(email=email, full_name=name, password_hash=hash_password(password), role=Role.SUPER_ADMIN))
    print(f"Created initial super admin: {email}")


if __name__ == "__main__":
    main()
