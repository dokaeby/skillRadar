/* SkillRadar 프론트엔드: 탭/언어/날짜 전환 + 카드 렌더링 */
(() => {
  interface TrendingItem {
    rank: number;
    repo_full_name: string;
    repo_url: string;
    description: string | null;
    stars: number;
    stars_today: number | null;
    language: string | null;
    topics: string[];
    summary: string[];
  }
  interface TrendingResponse {
    platform: string;
    date: string;
    items: TrendingItem[];
  }

  const state = {
    platform: 'claude',
    lang: 'ko',
    date: '',
    dates: [] as string[],
  };

  const grid = document.getElementById('grid') as HTMLElement;
  const empty = document.getElementById('empty') as HTMLElement;
  const dateSelect = document.getElementById('dateSelect') as HTMLSelectElement;
  const updatedAt = document.getElementById('updatedAt') as HTMLElement;
  const themeToggle = document.getElementById('themeToggle') as HTMLButtonElement;
  const langToggle = document.getElementById('langToggle') as HTMLElement;
  const platformTabs = document.getElementById('platformTabs') as HTMLElement;

  // 다크모드 초기화 (localStorage 우선)
  const savedTheme = localStorage.getItem('sr-theme');
  if (savedTheme === 'light') document.documentElement.classList.remove('dark');
  if (savedTheme === 'dark') document.documentElement.classList.add('dark');
  const isDark = () => document.documentElement.classList.contains('dark');
  themeToggle.textContent = isDark() ? '☀️' : '🌙';
  themeToggle.addEventListener('click', () => {
    const dark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('sr-theme', dark ? 'dark' : 'light');
    themeToggle.textContent = dark ? '☀️' : '🌙';
  });

  function setActiveLang(btn: HTMLButtonElement): void {
    document.querySelectorAll<HTMLButtonElement>('#langToggle button').forEach((b) => {
      const active = b === btn;
      b.classList.toggle('bg-slate-900', active);
      b.classList.toggle('text-white', active);
      b.classList.toggle('dark:bg-white', active);
      b.classList.toggle('dark:text-slate-900', active);
      b.classList.toggle('text-slate-500', !active);
      b.classList.toggle('dark:text-slate-400', !active);
    });
  }

  langToggle.querySelectorAll<HTMLButtonElement>('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.lang = btn.dataset.lang ?? 'ko';
      setActiveLang(btn);
      void loadTrending();
    });
  });

  platformTabs.querySelectorAll<HTMLButtonElement>('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.platform = btn.dataset.platform ?? 'claude';
      platformTabs.querySelectorAll('button').forEach((b) =>
        b.classList.toggle('tab-active', b === btn)
      );
      void loadDates();
      void loadTrending();
    });
  });

  dateSelect.addEventListener('change', () => {
    state.date = dateSelect.value;
    void loadTrending();
  });

  function skeletons(): void {
    grid.innerHTML = Array.from({ length: 6 }, () => `
      <div class="card rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-5">
        <div class="skeleton h-4 w-2/3 rounded mb-3"></div>
        <div class="skeleton h-3 w-full rounded mb-2"></div>
        <div class="skeleton h-3 w-5/6 rounded mb-2"></div>
        <div class="skeleton h-3 w-4/6 rounded"></div>
      </div>`).join('');
    empty.classList.add('hidden');
  }

  function fmtStars(n: number): string {
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return String(n);
  }

  function escapeHtml(s: unknown): string {
    const map: Record<string, string> = {
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    };
    return String(s ?? '').replace(/[&<>"']/g, (c) => map[c]);
  }

  function renderCard(item: TrendingItem): string {
    const topics = (item.topics || []).slice(0, 4)
      .map((t) => `<span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">${escapeHtml(t)}</span>`)
      .join('');
    const delta = item.stars_today;
    const deltaInner = delta === null || delta === undefined
      ? '<span class="text-slate-400">—</span>'
      : delta > 0
        ? `<span class="text-emerald-500 font-semibold">+${fmtStars(delta)}</span>`
        : '<span class="text-slate-400">±0</span>';
    const lines = (item.summary || []).map((l) =>
      `<li class="flex gap-2"><span class="text-slate-300 dark:text-slate-600 select-none">·</span><span>${escapeHtml(l)}</span></li>`
    ).join('');
    return `
    <article class="card fade-up rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-5 flex flex-col gap-3 hover:border-slate-300 dark:hover:border-slate-700 hover:shadow-lg hover:shadow-slate-900/5">
      <div class="flex items-start gap-3">
        <span class="rank-badge shrink-0 w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm text-slate-700 dark:text-slate-200">${item.rank}</span>
        <div class="min-w-0 flex-1">
          <a href="${item.repo_url}" target="_blank" rel="noopener"
             class="font-semibold text-[15px] leading-snug hover:underline decoration-slate-300 dark:decoration-slate-600 underline-offset-2 truncate block">
            ${escapeHtml(item.repo_full_name)}
          </a>
          <div class="flex items-center gap-2 mt-0.5 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
            ${item.language ? `<span class="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800">${escapeHtml(item.language)}</span>` : ''}
            <span>⭐ ${fmtStars(item.stars)}</span>
            <span>오늘 <span class="font-medium">${deltaInner}</span></span>
          </div>
        </div>
      </div>
      <ul class="text-[13px] leading-relaxed text-slate-600 dark:text-slate-300 space-y-1.5">${lines}</ul>
      <div class="flex items-center justify-between mt-auto pt-1">
        <div class="flex gap-1 flex-wrap">${topics}</div>
        <a href="${item.repo_url}" target="_blank" rel="noopener"
           class="shrink-0 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-85 transition-opacity">
          GitHub에서 보기 ↗
        </a>
      </div>
    </article>`;
  }

  async function loadDates(): Promise<void> {
    try {
      const res = await fetch(`/api/dates?platform=${state.platform}`);
      const data = (await res.json()) as { dates?: string[] };
      state.dates = data.dates ?? [];
      dateSelect.innerHTML = state.dates.length
        ? state.dates.map((d) => `<option value="${d}">${d}</option>`).join('')
        : '<option value="">—</option>';
      if (state.dates.length) {
        state.date = state.dates[0];
        dateSelect.value = state.date;
      }
    } catch {
      /* 날짜 목록 실패는 무시 */
    }
  }

  async function loadTrending(): Promise<void> {
    skeletons();
    try {
      const params = new URLSearchParams({ platform: state.platform, lang: state.lang });
      if (state.date) params.set('date', state.date);
      const res = await fetch(`/api/trending?${params.toString()}`);
      const data = (await res.json()) as TrendingResponse;
      if (!data.items || !data.items.length) {
        grid.innerHTML = '';
        empty.classList.remove('hidden');
        return;
      }
      empty.classList.add('hidden');
      grid.innerHTML = data.items.map(renderCard).join('');
      updatedAt.textContent = `업데이트 ${new Date().toLocaleString('ko-KR')}`;
    } catch {
      grid.innerHTML = '<p class="col-span-full text-center text-red-500 py-10">데이터를 불러오지 못했습니다.</p>';
    }
  }

  void loadDates().then(loadTrending);
})();
