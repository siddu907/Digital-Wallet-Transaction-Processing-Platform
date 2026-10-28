from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FinancialIdentifier(Base):
    __tablename__ = "financial_identifiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
