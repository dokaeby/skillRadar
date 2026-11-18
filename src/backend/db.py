"""DATABASE_URL 스킴에 따라 sqlite/postgres 엔진을 만들고 세션을 제공한다."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import Settings, get_settings
from backend.models import Base


def make_engine(database_url: str):
    """DATABASE_URL로 SQLAlchemy 엔진을 만든다. postgres는 psycopg 드라이버를 쓴다."""
    url = database_url
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # 서버리스 환경에서 인스턴스 수만큼 엔진이 생기므로 Postgres는 커넥션 풀을 작게 유지한다.
    pool_kwargs = (
        {"pool_size": 2, "max_overflow": 3, "pool_recycle": 300}
        if url.startswith("postgres")
        else {}
    )
    return create_engine(
        url, connect_args=connect_args, pool_pre_ping=True, **pool_kwargs
    )


@lru_cache
def get_engine():
    return make_engine(get_settings().database_url)


def init_db(engine=None) -> None:
    """테이블이 없으면 만든다. Render 무료 플랜 재시작 대응용 자동 마이그레이션."""
    eng = engine or get_engine()
    Base.metadata.create_all(eng)


def session_factory() -> sessionmaker[Session]:
    """앱/스케줄러가 공유하는 세션 팩토리."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Generator[Session]:
    """FastAPI Depends용 세션. 요청이 끝나면 닫는다."""
    session = session_factory()()
    try:
        yield session
    finally:
        session.close()
