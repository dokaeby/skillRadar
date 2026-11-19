/* Web Push 구독 처리 */
(() => {
  /** app.ts가 노출한 번역 함수. 없으면 한국어 폴백. */
  const T = (window as unknown as { SR_T?: (k: string) => string }).SR_T
    ?? ((k: string) => ({ pushOn: '알림 받기', pushOff: '알림 중' } as Record<string, string>)[k] ?? k);
  const btn = document.getElementById('pushBtn') as HTMLButtonElement | null;
  if (!btn) return;
  const pushBtn: HTMLButtonElement = btn;

  const pushSupported =
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window;

  /** iOS 기기 여부를 판별한다. */
  /** 입력: 없음 / 출력: boolean / 결과: 없음 */
  function isIos(): boolean {
    const ua = navigator.userAgent;
    return (
      /iphone|ipad|ipod/i.test(ua) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
    );
  }

  /** 푸시 미지원 브라우저/기기에 안내 alert를 표시한다. */
  /** 입력: 없음 / 출력: 없음 / 결과: alert 표시 */
  function showUnsupportedGuide(): void {
    if (isIos()) {
      alert(
        '아이폰에서는 홈 화면에 추가한 앱에서만 알림을 받을 수 있습니다.\n\n' +
          '1. Safari 공유 버튼(□↑) 탭\n' +
          '2. "홈 화면에 추가" 선택\n' +
          '3. 홈 화면의 SkillRadar를 실행한 뒤 다시 눌러주세요.'
      );
    } else {
      alert('이 브라우저는 웹 푸시를 지원하지 않습니다. Chrome을 사용해주세요.');
    }
  }

  /** base64url VAPID 공개키를 Uint8Array로 변환한다. */
  /** 입력: base64 — base64url 문자열 / 출력: Uint8Array / 결과: 없음 */
  function urlBase64ToUint8Array(base64: string): Uint8Array {
    const padding = '='.repeat((4 - (base64.length % 4)) % 4);
    const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(b64);
    return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
  }

  /** 현재 등록된 푸시 구독을 반환한다. */
  /** 입력: 없음 / 출력: PushSubscription|null / 결과: 없음 */
  async function currentSub(): Promise<PushSubscription | null> {
    const reg = await navigator.serviceWorker.ready;
    return reg.pushManager.getSubscription();
  }

  const pushBtnLabel = document.getElementById('pushBtnLabel') as HTMLElement | null;

  /** 구독 상태에 맞게 버튼 라벨/스타일을 갱신한다. */
  /** 입력: 없음 / 출력: Promise<void> / 결과: 버튼 DOM 갱신 */
  async function refreshBtn(): Promise<void> {
    const sub = await currentSub().catch(() => null);
    if (pushBtnLabel) pushBtnLabel.textContent = sub ? T('pushOff') : T('pushOn');
    pushBtn.classList.toggle('subscribed', !!sub);
  }

  pushBtn.addEventListener('click', () => {
    void (async () => {
      try {
        if (!pushSupported) {
          showUnsupportedGuide();
          return;
        }
        const sub = await currentSub();
        if (sub) {
          await fetch('/api/push/unsubscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sub.toJSON()),
          });
          await sub.unsubscribe();
        } else {
          const vapidRes = await fetch('/api/push/vapid-key');
          const { key } = (await vapidRes.json()) as { key: string };
          if (!key) {
            alert('푸시가 아직 설정되지 않았습니다.');
            return;
          }
          const reg = await navigator.serviceWorker.register('/sw.js');
          await navigator.serviceWorker.ready;
          const permission = await Notification.requestPermission();
          if (permission !== 'granted') return;
          const newSub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(key) as BufferSource,
          });
          await fetch('/api/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newSub.toJSON()),
          });
        }
        await refreshBtn();
      } catch (e) {
        console.error('push error', e);
      }
    })();
  });

  if (pushSupported) {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined);
    navigator.serviceWorker.ready.then(refreshBtn).catch(() => undefined);
  }
})();
