from app.core.security import hash_password
from app.models import Role, User, Wallet


def make_user(email: str, *, role: Role = Role.CUSTOMER) -> User:
    return User(email=email, full_name="Test User", password_hash=hash_password("FactoryPassword123!"), role=role)


def make_wallet(owner_id: int, *, currency: str = "INR", balance: str = "0.00") -> Wallet:
    return Wallet(owner_id=owner_id, currency=currency, available_balance=balance)
