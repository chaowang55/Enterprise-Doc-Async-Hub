from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    url = get_settings().database_url
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, **kwargs)


def session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def init_db():
    import app.models  # noqa: F401

    Base.metadata.create_all(get_engine())


if __name__ == "__main__":
    # Keep one canonical Base registry when this file is executed with -m.
    from app.db import init_db as initialize

    initialize()
