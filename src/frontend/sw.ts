/* SkillRadar service worker: Web Push 수신 */
/// <reference lib="webworker" />

interface PushPayload {
  title?: string;
  body?: string;
  url?: string;
}

const sw = self as unknown as ServiceWorkerGlobalScope;

/** 푸시 수신 시 OS 알림 표시.
 *  입력: event — PushEvent(페이로드 JSON) / 출력: 없음
 *  결과: showNotification으로 알림 표시, 클릭 시 data.url로 이동 */
sw.addEventListener('push', (event: PushEvent) => {
  let data: PushPayload = {
    title: 'SkillRadar',
    body: '새로운 트렌딩이 업데이트되었습니다.',
  };
  try {
    if (event.data) {
      data = { ...data, ...(event.data.json() as PushPayload) };
    }
  } catch {
    /* ignore */
  }
  event.waitUntil(
    sw.registration.showNotification(data.title || 'SkillRadar', {
      body: data.body || '',
      icon: '/static/icon.png',
      badge: '/static/icon.png',
      data: { url: data.url || '/' },
    })
  );
});

/** 알림 클릭 시 해당 URL을 새 탭/창에서 연다.
 *  입력: event — NotificationEvent / 출력: 없음
 *  결과: notification 닫기 + clients.openWindow */
sw.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  const url =
    (event.notification.data as { url?: string } | undefined)?.url || '/';
  event.waitUntil(sw.clients.openWindow(url));
});
