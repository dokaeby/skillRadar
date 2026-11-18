"""SQLAlchemy 모델. DATABASE_URL이 sqlite/postgres 어느 쪽이든 같은 스키마를 쓴다."""

import json
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    """플랫폼별 하루 수집 단위."""

    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("platform", "collected_date", name="uq_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    collected_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    items: Mapped[list["SnapshotItem"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", order_by="SnapshotItem.rank"
    )


class SnapshotItem(Base):
    """스냅샷 안의 저장소 1개 (랭킹 1개)."""

    __tablename__ = "snapshot_items"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "repo_full_name", name="uq_snapshot_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stars_today: Mapped[int | None] = mapped_column(Integer)  # 직전 스냅샷 대비 증가분
    language: Mapped[str | None] = mapped_column(String(100))
    topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    readme_excerpt: Mapped[str | None] = mapped_column(Text)
    summary_en: Mapped[list[str] | None] = mapped_column(JSON)
    summary_zh: Mapped[list[str] | None] = mapped_column(JSON)
    summary_ko: Mapped[list[str] | None] = mapped_column(JSON)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    snapshot: Mapped[Snapshot] = relationship(back_populates="items")

    def summary_for(self, lang: str) -> list[str]:
        """요청 언어에 맞는 3줄 요약을 돌려준다. 없으면 description 폴백."""
        key = {"en": self.summary_en, "zh": self.summary_zh, "ko": self.summary_ko}.get(lang)
        lines = list(key) if key else []
        if lines:
            return lines[:3]
        return [self.description or self.repo_full_name]


class PushSubscription(Base):
    """브라우저 Web Push 구독 정보."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    keys_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    @property
    def keys(self) -> dict[str, str]:
        return json.loads(self.keys_json)
