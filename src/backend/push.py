"""Web Push 발송. VAPID 키가 없으면 조용히 비활성화된다."""

import asyncio
import json
import logging
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models import PushSubscription, Snapshot, SnapshotItem

logger = logging.getLogger(__name__)


def subscribe(session: Session, endpoint: str, keys: dict[str, str]) -> PushSubscription:
    """구독 정보 upsert. 같은 endpoint는 갱신한다.

    입력: session — DB 세션; endpoint — 푸시 서비스 엔드포인트 URL;
        keys — {"p256dh": ..., "auth": ...} 구독 키
    출력: 저장(또는 갱신)된 PushSubscription 행
    결과: push_subscriptions 테이블에 커밋됨
    """
    row = session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    ).scalar_one_or_none()
    if row is None:
        row = PushSubscription(endpoint=endpoint, keys_json=json.dumps(keys))
        session.add(row)
    else:
        row.keys_json = json.dumps(keys)
    session.commit()
    return row


def unsubscribe(session: Session, endpoint: str) -> None:
    """endpoint 구독을 삭제한다.

    입력: session — DB 세션; endpoint — 삭제할 구독 엔드포인트
    출력: 없음
    결과: 해당 행이 push_subscriptions에서 삭제·커밋됨
    """
    session.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint))
    session.commit()


async def send_push(
    session: Session,
    settings: Settings,
    title: str,
    body: str,
    url: str = "/",
) -> int:
    """모든 구독자에게 푸시 발송. 성공 건수를 반환한다.

    입력: session — 구독 조회/삭제용 DB 세션; settings — VAPID 키;
        title/body/url — 알림 제목·본문·클릭 시 이동 URL
    출력: 발송 성공한 구독 수 (push 비활성 시 0)
    결과: 404/410 응답 구독은 만료로 간주해 삭제·커밋
    """
    if not settings.push_enabled:
        return 0
    from pywebpush import WebPushException, webpush  # 지연 import: 미설치 환경 배려

    subs = session.execute(select(PushSubscription)).scalars().all()
    sent = 0
    for sub in subs:
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": sub.keys,
                },
                data=json.dumps({"title": title, "body": body, "url": url}),
                vapid_private_key=settings.vapid_private_key.get_secret_value(),
                vapid_claims={"sub": settings.vapid_subject},
            )
            sent += 1
        except WebPushException as exc:
            # 404/410은 구독 만료 → 구독 삭제
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                session.delete(sub)
            logger.info("푸시 실패 %s (status=%s)", sub.endpoint[:60], status)
        except Exception as exc:  # noqa: BLE001
            logger.warning("푸시 예외: %s", exc)
    session.commit()
    return sent


async def notify_daily_top(session: Session, settings: Settings) -> int:
    """수집 완료 후 각 플랫폼 Top1을 푸시로 알린다.

    입력: session — 최신 스냅샷 조회용 DB 세션; settings — VAPID 키
    출력: 전체 발송 성공 건수 합계 (push 비활성·스냅샷 없음 시 0)
    결과: 플랫폼별 Top1 repo를 제목/본문으로 구독자 전체에 발송
    """
    if not settings.push_enabled:
        return 0
    latest_date = session.execute(
        select(Snapshot.collected_date)
        .order_by(Snapshot.collected_date.desc())
        .limit(1)
    ).scalar()
    if latest_date is None:
        return 0
    total = 0
    for platform in ("claude", "chatgpt", "gemini"):
        snap = session.execute(
            select(Snapshot).where(
                Snapshot.platform == platform, Snapshot.collected_date == latest_date
            )
        ).scalar_one_or_none()
        if snap is None or not snap.items:
            continue
        top = snap.items[0]
        total += await send_push(
            session,
            settings,
            title=f"{platform.capitalize()} Top 1",
            body=f"{top.repo_full_name} ⭐{top.stars}",
            url=f"/?platform={platform}",
        )
    return total


WEEKLY_DIGEST_DAYS = 7


async def notify_weekly_digest(session: Session, settings: Settings) -> int:
    """최근 7일 랭킹 변화를 요약한 주간 digest 푸시 1건을 발송한다.

    입력: session — 스냅샷/구독 조회용 DB 세션; settings — VAPID 키
    출력: 발송 성공 구독 수 (push 비활성·데이터 없음 시 0)
    결과: 신규 진입·이탈·stars_today 합계·급상승 Top3를 본문에 담아 발송
    """
    if not settings.push_enabled:
        return 0
    today = date.today()
    since = today - timedelta(days=WEEKLY_DIGEST_DAYS)

    # 윈도우 내 등장 repo 통계
    rows = session.execute(
        select(SnapshotItem, Snapshot)
        .join(Snapshot, SnapshotItem.snapshot_id == Snapshot.id)
        .where(Snapshot.collected_date >= since)
    ).all()
    if not rows:
        return 0
    gain: dict[str, int] = {}
    window_repos: set[str] = set()
    for item, _snap in rows:
        window_repos.add(item.repo_full_name)
        gain[item.repo_full_name] = gain.get(item.repo_full_name, 0) + (item.stars_today or 0)

    # 윈도우 이전에 등장한 적 있는 repo (이탈 계산용)
    prior = session.execute(
        select(SnapshotItem.repo_full_name)
        .join(Snapshot, SnapshotItem.snapshot_id == Snapshot.id)
        .where(Snapshot.collected_date < since)
        .distinct()
    ).scalars().all()
    prior_set = set(prior)
    new_entries = window_repos - prior_set
    exited = prior_set - window_repos

    # 주간 stars 증가 Top3 (표시용 최신 item 조회)
    top_names = sorted(gain.items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_label = ", ".join(f"{name} +{g}" for name, g in top_names if g > 0) or "-"

    total_gain = sum(gain.values())
    body = (
        f"신규 {len(new_entries)}개 · 이탈 {len(exited)}개 · "
        f"주간 star 증가 {total_gain:,}\n급상승: {top_label}"
    )
    return await send_push(
        session,
        settings,
        title="SkillRadar 주간 리포트",
        body=body,
        url="/",
    )
