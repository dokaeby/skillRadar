"use strict";
/* SkillRadar service worker: Web Push 수신 */
/// <reference lib="webworker" />
const sw = self;
sw.addEventListener('push', (event) => {
    let data = {
        title: 'SkillRadar',
        body: '새로운 트렌딩이 업데이트되었습니다.',
    };
    try {
        if (event.data) {
            data = { ...data, ...event.data.json() };
        }
    }
    catch {
        /* ignore */
    }
    event.waitUntil(sw.registration.showNotification(data.title || 'SkillRadar', {
        body: data.body || '',
        icon: '/static/icon.png',
        badge: '/static/icon.png',
        data: { url: data.url || '/' },
    }));
});
sw.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const url = event.notification.data?.url || '/';
    event.waitUntil(sw.clients.openWindow(url));
});
