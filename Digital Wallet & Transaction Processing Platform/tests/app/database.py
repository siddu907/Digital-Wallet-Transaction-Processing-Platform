from collections.abc import Generator
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.config import settings


class Base(DeclarativeBase):
    pass


_engine_options: dict[str, object] = {"pool_pre_ping": True}
if make_url(settings.database_url).get_backend_name() in {"postgresql", "mysql", "mariadb"}:
    _engine_options.update(
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )

engine = create_engine(settings.database_url, **_engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
