from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import Role
from app.database import Base


class RoleRecord(Base):
    __tablename__ = "roles"

    name: Mapped[Role] = mapped_column(Enum(Role, name="role"), primary_key=True)
    description: Mapped[str] = mapped_column(default="", nullable=False)
