"use strict";
/* Web Push 구독 처리 */
(() => {
    const btn = document.getElementById('pushBtn');
    if (!btn)
        return;
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        btn.style.display = 'none';
        return;
    }
    const pushBtn = btn;
    function urlBase64ToUint8Array(base64) {
        const padding = '='.repeat((4 - (base64.length % 4)) % 4);
        const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
        const raw = atob(b64);
        return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
    }
    async function currentSub() {
        const reg = await navigator.serviceWorker.ready;
        return reg.pushManager.getSubscription();
    }
    async function refreshBtn() {
        const sub = await currentSub().catch(() => null);
        if (sub) {
            pushBtn.textContent = '🔔 알림 중';
            pushBtn.classList.add('subscribed');
        }
        else {
            pushBtn.textContent = '🔔 알림 받기';
            pushBtn.classList.remove('subscribed');
        }
    }
    pushBtn.addEventListener('click', () => {
        void (async () => {
            try {
                const sub = await currentSub();
                if (sub) {
                    await fetch('/api/push/unsubscribe', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(sub.toJSON()),
                    });
                    await sub.unsubscribe();
                }
                else {
                    const vapidRes = await fetch('/api/push/vapid-key');
                    const { key } = (await vapidRes.json());
                    if (!key) {
                        alert('푸시가 아직 설정되지 않았습니다.');
                        return;
                    }
                    const reg = await navigator.serviceWorker.register('/sw.js');
                    await navigator.serviceWorker.ready;
                    const permission = await Notification.requestPermission();
                    if (permission !== 'granted')
                        return;
                    const newSub = await reg.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(key),
                    });
                    await fetch('/api/push/subscribe', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(newSub.toJSON()),
                    });
                }
                await refreshBtn();
            }
            catch (e) {
                console.error('push error', e);
            }
        })();
    });
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => undefined);
        navigator.serviceWorker.ready.then(refreshBtn).catch(() => undefined);
    }
})();
