"""DATABASE_URL 스킴에 따라 sqlite/postgres 엔진을 만들고 세션을 제공한다."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.models import Base


def make_engine(database_url: str) -> Engine:
    """DATABASE_URL로 SQLAlchemy 엔진을 만든다. postgres는 psycopg 드라이버를 쓴다.

    입력: database_url — sqlite:/// 또는 postgresql:// 접속 문자열
    출력: 생성된 SQLAlchemy Engine (풀 설정 포함)
    결과: postgres일 때 psycopg prepared statement를 비활성화해
        Supabase pooler의 DuplicatePreparedStatement를 방지
    """
    url = database_url
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    else:
        # Supabase pooler(특히 transaction 모드)에서는 서버 커넥션이
        # 여러 클라이언트에 공유되어 prepared statement 이름이 충돌한다
        # (DuplicatePreparedStatement). psycopg의 자동 prepare를 끈다.
        connect_args = {"prepare_threshold": None}
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
def get_engine() -> Engine:
    """설정의 database_url로 엔진을 만든다. 프로세스당 1회 캐시.

    입력: 없음 (get_settings()에서 읽음)
    출력: 캐시된 SQLAlchemy Engine
    결과: 최초 호출 시에만 make_engine 실행
    """
    return make_engine(get_settings().database_url)


def init_db(engine: Engine | None = None) -> None:
    """테이블이 없으면 만든다. Render 무료 플랜 재시작 대응용 자동 마이그레이션.

    입력: engine — 사용할 Engine (None이면 get_engine())
    출력: 없음
    결과: Base.metadata의 모든 테이블이 DB에 생성·커밋됨
    """
    eng = engine or get_engine()
    Base.metadata.create_all(eng)


@lru_cache
def session_factory() -> sessionmaker[Session]:
    """앱/스케줄러가 공유하는 세션 팩토리.

    입력: 없음
    출력: get_engine()에 바인딩된 sessionmaker
    결과: expire_on_commit=False로 커밋 후 객체 만료 방지
    """
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI Depends용 세션. 요청이 끝나면 닫는다.

    입력: 없음
    출력: yield된 DB Session (의존성 주입으로 사용)
    결과: 요청 종료 시 세션 close 보장
    """
    session = session_factory()()
    try:
        yield session
    finally:
        session.close()
