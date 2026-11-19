"""Web Push 발송. VAPID 키가 없으면 조용히 비활성화된다."""

import asyncio
import json
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models import PushSubscription, Snapshot

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
