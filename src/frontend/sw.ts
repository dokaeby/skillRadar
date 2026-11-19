/* SkillRadar service worker: Web Push 수신 */
/// <reference lib="webworker" />

interface PushPayload {
  title?: string;
  body?: string;
  url?: string;
}

const sw = self as unknown as ServiceWorkerGlobalScope;

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

sw.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  const url =
    (event.notification.data as { url?: string } | undefined)?.url || '/';
  event.waitUntil(sw.clients.openWindow(url));
});
