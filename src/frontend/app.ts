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
    license?: string | null;
    topics: string[];
    summary: string[];
    platform?: string | null;
    taxonomy?: string | null;
    rank_score?: number | null;
    summary_status?: string | null;
    appearances?: number | null;
    readme_excerpt?: string | null;
    summaries?: Record<string, string[]> | null;
    related_topics?: string[] | null;
    collected_date?: string | null;
    snapshot_platform?: string | null;
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
    topic: null as string | null,
    topicPlatform: 'all',
    period: 'daily' as 'daily' | 'week' | 'month',
    taxFilter: 'all',
    minStars: 0,
    view: 'list' as 'list' | 'repo',
    lastItems: [] as TrendingItem[],
  };

  const grid = document.getElementById('grid') as HTMLElement;
  const empty = document.getElementById('empty') as HTMLElement;
  const dateSelect = document.getElementById('dateSelect') as HTMLSelectElement;
  const updatedAt = document.getElementById('updatedAt') as HTMLElement;
  const themeToggle = document.getElementById('themeToggle') as HTMLButtonElement;
  const themeIconSun = document.getElementById('themeIcon') as HTMLElement;
  const themeIconMoon = document.getElementById('themeIconMoon') as HTMLElement;
  const langToggle = document.getElementById('langToggle') as HTMLElement;
  const platformTabs = document.getElementById('platformTabs') as HTMLElement;
  const trendBar = document.getElementById('trendBar') as HTMLElement;
  const topicList = document.getElementById('topicList') as HTMLElement;
  const topicHeader = document.getElementById('topicHeader') as HTMLElement;
  const relatedTopics = document.getElementById('relatedTopics') as HTMLElement;
  let allTopics: { topic: string; count: number }[] = [];
  const topicTitle = document.getElementById('topicTitle') as HTMLElement;
  const topicCount = document.getElementById('topicCount') as HTMLElement;
  const topicBack = document.getElementById('topicBack') as HTMLElement;
  const topicPlatformTabs = document.getElementById('topicPlatformTabs') as HTMLElement;
  const periodTabs = document.getElementById('periodTabs') as HTMLElement;
  const taxSelect = document.getElementById('taxSelect') as HTMLSelectElement;
  const minStarsRange = document.getElementById('minStars') as HTMLInputElement;
  const minStarsLabel = document.getElementById('minStarsLabel') as HTMLElement;
  const filterBar = document.getElementById('filterBar') as HTMLElement;
  const repoView = document.getElementById('repoView') as HTMLElement;
  const dateLabelWrap = document.getElementById('dateLabelWrap') as HTMLElement;

  // ---- UI i18n (ko/en/zh) ----
  const I18N: Record<string, Record<string, string>> = {
    ko: {
      today: '오늘', noLicense: '라이선스 없음', updated: '업데이트',
      subtitle: 'AI 도구 트렌딩', dateLabel: '기준일',
      periodDaily: '일간', periodWeek: '주간', periodMonth: '월간',
      topicsTitle: '관심 주제', topicsWindow: '최근 30일',
      backToTrending: '트렌딩으로 돌아가기',
      emptyTitle: '아직 수집된 데이터가 없습니다',
      emptyDesc: '매일 KST 06:00 자동 수집되거나, 관리자가 /api/admin/refresh를 호출하세요.',
      topicNoRepos: '이 주제의 저장소가 없습니다',
      topicNoReposDesc: '다른 주제를 선택하거나 트렌딩으로 돌아가세요.',
      topicsEmpty: '주제 데이터가 없습니다',
      topicsLoadFail: '주제를 불러오지 못했습니다',
      loadFail: '데이터를 불러오지 못했습니다.',
      filterTax: '분류', filterTaxAll: '전체', filterMinStars: '최소 스타',
      appearancesShort: '회',
      detailCollected: '수집일', detailPlatform: '플랫폼',
      detailReadme: 'README', detailSummary: '요약', detailRelated: '관련 주제',
      detailNotFound: '수집된 저장소가 아닙니다',
      topicCountFmt: '최근 30일 {count}개 저장소',
      footerLeft: 'GitHub Search API · 일일 Top 10 · LLM 3줄 요약',
      pushOn: '알림 받기', pushOff: '알림 중',
    },
    en: {
      today: 'today', noLicense: 'No license', updated: 'Updated',
      subtitle: 'AI tooling trending', dateLabel: 'Date',
      periodDaily: 'Daily', periodWeek: 'Weekly', periodMonth: 'Monthly',
      topicsTitle: 'Topics', topicsWindow: 'Last 30 days',
      backToTrending: 'Back to trending',
      emptyTitle: 'No data collected yet',
      emptyDesc: 'Collected daily at 06:00 KST, or call /api/admin/refresh.',
      topicNoRepos: 'No repos for this topic',
      topicNoReposDesc: 'Pick another topic or go back to trending.',
      topicsEmpty: 'No topic data',
      topicsLoadFail: 'Failed to load topics',
      loadFail: 'Failed to load data.',
      filterTax: 'Category', filterTaxAll: 'All', filterMinStars: 'Min stars',
      appearancesShort: '×',
      detailCollected: 'Collected', detailPlatform: 'Platform',
      detailReadme: 'README', detailSummary: 'Summary', detailRelated: 'Related topics',
      detailNotFound: 'Repo not found in collected data',
      topicCountFmt: '{count} repos in last 30 days',
      footerLeft: 'GitHub Search API · Daily Top 10 · LLM 3-line summary',
      pushOn: 'Notify me', pushOff: 'Notifying',
    },
    zh: {
      today: '今日', noLicense: '无许可证', updated: '更新于',
      subtitle: 'AI 工具趋势', dateLabel: '日期',
      periodDaily: '每日', periodWeek: '每周', periodMonth: '每月',
      topicsTitle: '关注主题', topicsWindow: '近30天',
      backToTrending: '返回趋势',
      emptyTitle: '尚无收集数据',
      emptyDesc: '每天 KST 06:00 自动收集，或调用 /api/admin/refresh。',
      topicNoRepos: '该主题暂无仓库',
      topicNoReposDesc: '请选择其他主题或返回趋势页。',
      topicsEmpty: '暂无主题数据',
      topicsLoadFail: '主题加载失败',
      loadFail: '数据加载失败。',
      filterTax: '分类', filterTaxAll: '全部', filterMinStars: '最低星标',
      appearancesShort: '次',
      detailCollected: '收集日期', detailPlatform: '平台',
      detailReadme: 'README', detailSummary: '摘要', detailRelated: '相关主题',
      detailNotFound: '未找到该仓库',
      topicCountFmt: '近30天 {count} 个仓库',
      footerLeft: 'GitHub Search API · 每日 Top 10 · LLM 三行摘要',
      pushOn: '接收通知', pushOff: '通知中',
    },
  };

  /** 현재 언어의 UI 문자열을 반환한다. */
  /** 입력: key — I18N 키 / 출력: 번역 문자열 / 결과: window.SR_T에도 노출 */
  function t(key: string): string {
    return I18N[state.lang]?.[key] ?? I18N.ko[key] ?? key;
  }
  (window as unknown as { SR_T: (k: string) => string }).SR_T = t;

  /** data-i18n 속성 요소들의 텍스트를 현재 언어로 갱신한다. */
  /** 입력: 없음 / 출력: 없음 / 결과: DOM 텍스트 갱신 */
  function applyI18n(): void {
    document.querySelectorAll<HTMLElement>('[data-i18n]').forEach((el) => {
      el.textContent = t(el.dataset.i18n ?? '');
    });
    document.title = 'SkillRadar — ' + t('subtitle');
  }

  const ICON = {
    star: '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.2 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8z"/></svg>',
    trending: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg>',
    arrow: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M9 7h8v8"/></svg>',
  };

  /** 테마 아이콘(해/달) 표시를 현재 다크모드 상태에 맞춰 전환한다. */
  /** 입력: 없음 / 출력: 없음 / 결과: DOM 클래스 토글 */
  function syncThemeIcon(): void {
    const dark = isDark();
    themeIconSun.classList.toggle('hidden', dark);
    themeIconMoon.classList.toggle('hidden', !dark);
  }

  // 다크모드 초기화 (localStorage 우선)
  const savedTheme = localStorage.getItem('sr-theme');
  if (savedTheme === 'dark') document.documentElement.classList.add('dark');
  else document.documentElement.classList.remove('dark');
  const isDark = () => document.documentElement.classList.contains('dark');
  syncThemeIcon();
  themeToggle.addEventListener('click', () => {
    const dark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('sr-theme', dark ? 'dark' : 'light');
    syncThemeIcon();
  });

  /** 언어 토글 버튼 중 활성 버튼 스타일을 갱신한다. */
  /** 입력: btn — 클릭된 언어 버튼 / 출력: 없음 / 결과: 버튼 CSS 클래스 토글 */
  function setActiveLang(btn: HTMLButtonElement): void {
    document.querySelectorAll<HTMLButtonElement>('#langToggle button').forEach((b) => {
      const active = b === btn;
      b.classList.toggle('bg-white', active);
      b.classList.toggle('text-slate-900', active);
      b.classList.toggle('font-semibold', active);
      b.classList.toggle('text-slate-500', !active);
      b.classList.toggle('dark:text-slate-400', !active);
      b.classList.toggle('hover:text-slate-700', !active);
      b.classList.toggle('dark:hover:text-slate-200', !active);
    });
  }

  langToggle.querySelectorAll<HTMLButtonElement>('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.lang = btn.dataset.lang ?? 'ko';
      setActiveLang(btn);
      applyI18n();
      if (state.view === 'repo') void loadRepoDetail();
      else if (state.period === 'daily') void loadTrending();
      else void loadRanking();
    });
  });

  platformTabs.querySelectorAll<HTMLButtonElement>('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.platform = btn.dataset.platform ?? 'claude';
      platformTabs.querySelectorAll('button').forEach((b) =>
        b.classList.toggle('tab-active', b === btn)
      );
      void loadDates();
      if (state.period === 'daily') void loadTrending();
      else void loadRanking();
    });
  });

  dateSelect.addEventListener('change', () => {
    state.date = dateSelect.value;
    if (state.period === 'daily') void loadTrending();
  });

  periodTabs.querySelectorAll<HTMLButtonElement>('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.period = (btn.dataset.period ?? 'daily') as 'daily' | 'week' | 'month';
      periodTabs.querySelectorAll('button').forEach((b) =>
        b.classList.toggle('tab-active', b === btn)
      );
      // 일간만 날짜 선택기를 쓴다
      dateLabelWrap.classList.toggle('hidden', state.period !== 'daily');
      if (state.period === 'daily') {
        void loadDates().then(loadTrending);
      } else {
        void loadRanking();
      }
    });
  });

  taxSelect.addEventListener('change', () => {
    state.taxFilter = taxSelect.value;
    renderFiltered();
  });
  minStarsRange.addEventListener('input', () => {
    state.minStars = Number(minStarsRange.value);
    minStarsLabel.textContent = fmtStars(state.minStars);
    renderFiltered();
  });

  /** 현재 필터를 통과하는 아이템만 렌더링한다. */
  /** 입력: 없음 / 출력: 없음 / 결과: grid DOM 갱신 */
  function renderFiltered(): void {
    const items = state.lastItems.filter(passFilters);
    if (!items.length) {
      grid.innerHTML = '';
      emptyTitle.textContent = t('emptyTitle');
      emptyDesc.textContent = t('emptyDesc');
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    grid.innerHTML = items.map(renderCard).join('');
  }

  /** 아이템이 taxonomy/최소 star 필터를 통과하는지 판정한다. */
  /** 입력: item — TrendingItem / 출력: boolean / 결과: 없음 */
  function passFilters(item: TrendingItem): boolean {
    if (state.taxFilter !== 'all' && item.taxonomy !== state.taxFilter) return false;
    if (item.stars < state.minStars) return false;
    return true;
  }

  /** 로딩 중 카드 자리표시자(skeleton)를 그리드에 렌더링한다. */
  /** 입력: 없음 / 출력: 없음 / 결과: grid.innerHTML 교체 */
  function skeletons(): void {
    grid.innerHTML = Array.from({ length: 6 }, () => `
      <div class="card rounded-2xl p-5">
        <div class="skeleton h-4 w-2/3 mb-3"></div>
        <div class="skeleton h-3 w-full mb-2"></div>
        <div class="skeleton h-3 w-5/6 mb-4"></div>
        <div class="skeleton h-8 w-full rounded-lg mb-3"></div>
        <div class="flex gap-2">
          <div class="skeleton h-5 w-16 rounded-full"></div>
          <div class="skeleton h-5 w-20 rounded-full"></div>
          <div class="skeleton h-5 w-14 rounded-full"></div>
        </div>
      </div>`).join('');
    empty.classList.add('hidden');
  }

  /** star 수를 읽기 쉬운 형태로 축약한다. */
  /** 입력: n — star 수 / 출력: "1.2k" 등 문자열 / 결과: 없음 */
  function fmtStars(n: number): string {
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return String(n);
  }

  /** SPDX 라이선스 ID를 짧은 표시용 문자열로 변환한다. */
  /** 입력: license — SPDX ID / 출력: 축약 문자열 / 결과: 없음 */
  function licenseShort(license: string): string {
    const map: Record<string, string> = {
      'Apache-2.0': 'Apache-2.0', 'MIT': 'MIT', 'BSD-2-Clause': 'BSD-2',
      'BSD-3-Clause': 'BSD-3', 'GPL-3.0': 'GPL-3', 'GPL-2.0': 'GPL-2',
      'AGPL-3.0': 'AGPL-3', 'LGPL-3.0': 'LGPL-3', 'MPL-2.0': 'MPL-2.0',
      'ISC': 'ISC', 'Unlicense': 'Unlicense', '0BSD': '0BSD',
      'CC0-1.0': 'CC0', 'EPL-2.0': 'EPL-2', 'BSL-1.0': 'BSL',
      'Elastic-2.0': 'Elastic-2', 'MS-PL': 'MS-PL', 'Zlib': 'Zlib',
      'WTFPL': 'WTFPL', 'Python-2.0': 'PSF', 'Artistic-2.0': 'Artistic',
    };
    if (map[license]) return map[license];
    const m = license.match(/^GPL-(\d+\.0)/);
    if (m) return `GPL-${m[1]}`;
    const b = license.match(/^BSD-(\d)-Clause/);
    if (b) return `BSD-${b[1]}`;
    return license.length > 12 ? license.slice(0, 12) : license;
  }

  /** HTML 특수문자를 이스케이프해 XSS를 방지한다. */
  /** 입력: s — 임의 값 / 출력: 이스케이프된 문자열 / 결과: 없음 */
  function escapeHtml(s: unknown): string {
    const map: Record<string, string> = {
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    };
    return String(s ?? '').replace(/[&<>"']/g, (c) => map[c]);
  }

  /** TrendingItem 1개를 카드 HTML 문자열로 렌더링한다. */
  /** 입력: item — API 응답 아이템 / 출력: 카드 HTML / 결과: 없음 */
  function renderCard(item: TrendingItem): string {
    const topics = (item.topics || []).slice(0, 4)
      .map((t) => `<span class="topic-chip text-[10px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-white/[.05] border border-slate-200 dark:border-white/[.07] text-slate-600 dark:text-slate-400">${escapeHtml(t)}</span>`)
      .join('');
    const delta = item.stars_today;
    const deltaInner = delta === null || delta === undefined
      ? '<span class="text-slate-500 dark:text-slate-500">—</span>'
      : delta > 0
        ? `<span class="text-emerald-400 font-semibold inline-flex items-center gap-1">${ICON.trending}+${fmtStars(delta)}</span>`
        : '<span class="text-slate-500 dark:text-slate-500">±0</span>';
    const lines = (item.summary || []).map((l) =>
      `<li class="flex gap-2.5"><span class="mt-[7px] w-1 h-1 rounded-full bg-slate-400/70 dark:bg-slate-500/60 shrink-0"></span><span class="line-clamp-3">${escapeHtml(l)}</span></li>`
    ).join('');
    const description = item.description
      ? `<p class="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 leading-relaxed mt-1">${escapeHtml(item.description)}</p>`
      : '';
    return `
    <article class="card fade-up rounded-2xl p-5 flex flex-col gap-3.5">
      <div class="flex items-start gap-3">
        <span class="rank-badge shrink-0 w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm text-slate-700 dark:text-slate-200">${item.rank}</span>
        <div class="min-w-0 flex-1">
          <a href="/repo/${item.repo_full_name}"
             class="font-semibold text-[15px] leading-snug text-slate-800 dark:text-slate-100 hover:text-blue-500 dark:hover:text-blue-400 underline-offset-4 decoration-slate-400/50 hover:underline truncate block transition-colors">
            ${escapeHtml(item.repo_full_name)}
          </a>
          ${description}
          <span class="inline-flex items-center gap-1.5 flex-wrap">
            ${item.platform ? `<span class="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide ${PLATFORM_BADGE[item.platform] ?? 'text-slate-500'}"><span class="w-1.5 h-1.5 rounded-full ${PLATFORM_DOT[item.platform] ?? 'bg-slate-500'}"></span>${item.platform}</span>` : ''}
            ${item.taxonomy ? `<span class="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-indigo-100 dark:bg-indigo-400/15 border border-indigo-300 dark:border-indigo-400/30 text-indigo-700 dark:text-indigo-300">${escapeHtml(item.taxonomy)}</span>` : ''}
            ${item.appearances && item.appearances > 1 ? `<span class="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-sky-100 dark:bg-sky-400/15 border border-sky-300 dark:border-sky-400/30 text-sky-700 dark:text-sky-300">${item.appearances}${t('appearancesShort')}</span>` : ''}
          </span>
          <div class="flex items-center gap-3 mt-2 text-xs text-slate-600 dark:text-slate-400 flex-wrap">
            ${item.license
              ? `<span class="px-2 py-0.5 rounded-md font-bold text-[10px] tracking-wide bg-amber-100 dark:bg-amber-400/15 border border-amber-300 dark:border-amber-400/30 text-amber-800 dark:text-amber-300" title="License: ${escapeHtml(item.license)}">${escapeHtml(licenseShort(item.license))}</span>`
              : `<span class="px-2 py-0.5 rounded-md text-[10px] tracking-wide bg-slate-100 dark:bg-white/[.04] border border-slate-200 dark:border-white/[.07] text-slate-400 dark:text-slate-500">${t('noLicense')}</span>`}
            ${item.language ? `<span class="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-white/[.05] border border-slate-200 dark:border-white/[.07] font-medium text-slate-700 dark:text-slate-200">${escapeHtml(item.language)}</span>` : ''}
            <span class="inline-flex items-center gap-1">${ICON.star}<span class="font-medium text-slate-600 dark:text-slate-300">${fmtStars(item.stars)}</span></span>
            <span class="inline-flex items-center gap-1">${t('today')} ${deltaInner}</span>
          </div>
        </div>
      </div>
      <ul class="text-[13px] leading-relaxed text-slate-600 dark:text-slate-300 space-y-2">${lines}</ul>
      <div class="flex items-center justify-between gap-2 mt-auto pt-2.5 border-t border-slate-200/80 dark:border-white/[.05]">
        <div class="flex gap-1.5 flex-wrap">${topics}</div>
        <a href="${item.repo_url}" target="_blank" rel="noopener"
           class="shrink-0 inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-white/[.06] border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-white/[.12] transition-colors">
          GitHub ${ICON.arrow}
        </a>
      </div>
    </article>`;
  }

  const PLATFORM_BADGE: Record<string, string> = {
    claude: 'text-[#b4552d] dark:text-claude', chatgpt: 'text-[#0b7a5c] dark:text-chatgpt', gemini: 'text-[#2b63d9] dark:text-gemini',
  };
  const PLATFORM_DOT: Record<string, string> = {
    claude: 'bg-claude', chatgpt: 'bg-chatgpt', gemini: 'bg-gemini',
  };

  /** 토픽 검색 결과를 그리드에 렌더링한다. */
  /** 입력: data — /api/topic-repos 응답 / 출력: 없음 / 결과: grid/empty DOM 갱신 */
  function renderTopicRepos(data: TrendingResponse): void {
    state.lastItems = data.items ?? [];
    if (!state.lastItems.length) {
      grid.innerHTML = '';
      emptyTitle.textContent = t('topicNoRepos');
      emptyDesc.textContent = t('topicNoReposDesc');
      empty.classList.remove('hidden');
      return;
    }
    renderFiltered();
  }

  /** 인기 토픽 목록을 API에서 가져와 사이드바에 렌더링한다. */
  /** 입력: 없음 / 출력: Promise<void> / 결과: topicList DOM 갱신, allTopics 저장 */
  async function loadTopics(): Promise<void> {
    try {
      const res = await fetch('/api/topics');
      const data = (await res.json()) as { topics?: { topic: string; count: number }[] };
      const topics = data.topics ?? [];
      allTopics = topics;
      if (!topics.length) {
        topicList.innerHTML = `<p class="text-xs text-slate-500 px-2 py-3">${t('topicsEmpty')}</p>`;
        return;
      }
      topicList.innerHTML = topics.map((t) => `
        <button class="topic-btn shrink-0 lg:w-full text-left px-3 py-2 rounded-lg text-[13px] font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/[.05] dark:hover:bg-white/[.05] hover:text-slate-800 dark:hover:text-slate-200 transition-colors flex items-center justify-between gap-2"
                data-topic="${escapeHtml(t.topic)}">
          <span class="truncate"># ${escapeHtml(t.topic)}</span>
          <span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 dark:bg-white/[.05] border border-slate-200 dark:border-white/[.08] text-slate-600 dark:text-slate-500">${t.count}</span>
        </button>`).join('');
      topicList.querySelectorAll<HTMLButtonElement>('.topic-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const topic = btn.dataset.topic ?? '';
          const count = Number(btn.querySelector('span:last-child')?.textContent ?? 0);
          selectTopic(topic, count);
        });
      });
    } catch {
      topicList.innerHTML = `<p class="text-xs text-slate-500 px-2 py-3">${t('topicsLoadFail')}</p>`;
    }
  }

  /** 선택된 토픽 버튼에 활성 스타일을 적용한다. */
  /** 입력: topic — 선택 토픽명 또는 null / 출력: 없음 / 결과: 버튼 CSS 토글 */
  function markActiveTopic(topic: string | null): void {
    topicList.querySelectorAll<HTMLButtonElement>('.topic-btn').forEach((b) => {
      const active = b.dataset.topic === topic;
      b.classList.toggle('bg-slate-200/70', active);
      b.classList.toggle('dark:bg-white/[.07]', active);
      b.classList.toggle('text-slate-800', active);
      b.classList.toggle('dark:text-slate-200', active);
      b.classList.toggle('text-slate-500', !active);
      b.classList.toggle('dark:text-slate-400', !active);
    });
  }

  /** 토픽 상세 보기로 전환하고 관련 데이터를 로드한다. */
  /** 입력: topic — 토픽명, count — 저장소 수 / 출력: 없음 / 결과: state 갱신 + API 로드 트리거 */
  function selectTopic(topic: string, count: number): void {
    state.topic = topic;
    state.topicPlatform = 'all';
    markActiveTopic(topic);
    topicTitle.textContent = `#${topic}`;
    topicCount.textContent = t('topicCountFmt').replace('{count}', String(count));
    topicHeader.classList.remove('hidden');
    trendBar.classList.add('hidden');
    syncTopicPlatformTabs();
    void loadTopicRepos();
    void loadRelatedTopics(topic);
  }

  /** 선택 토픽과 공기반으로 등장한 관련 토픽을 로드·렌더링한다. */
  /** 입력: topic — 기준 토픽 / 출력: Promise<void> / 결과: relatedTopics DOM 갱신 */
  async function loadRelatedTopics(topic: string): Promise<void> {
    relatedTopics.innerHTML = '';
    try {
      const res = await fetch(`/api/related-topics?topic=${encodeURIComponent(topic)}`);
      const data = (await res.json()) as { related?: { topic: string; score: number }[] };
      const related = (data.related ?? []).filter((r) => r.topic !== topic).slice(0, 8);
      if (!related.length) return;
      const label = document.createElement('span');
      label.className = 'text-[10px] uppercase tracking-wider text-slate-400 self-center mr-1';
      label.textContent = '관련 주제';
      relatedTopics.appendChild(label);
      for (const r of related) {
        const btn = document.createElement('button');
        btn.className = 'px-2.5 py-1 rounded-full text-[11px] font-medium bg-white/[.04] border border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 hover:border-[#d97757]/50 hover:text-[#d97757] transition-colors';
        btn.textContent = `#${r.topic}`;
        btn.addEventListener('click', () => {
          const t = allTopics.find((x) => x.topic === r.topic);
          selectTopic(r.topic, t?.count ?? 0);
        });
        relatedTopics.appendChild(btn);
      }
    } catch {
      /* 관련 주제 실패는 무시 */
    }
  }

  /** 토픽 상세에서 트렌딩 뷰로 복귀한다. */
  /** 입력: 없음 / 출력: 없음 / 결과: state 초기화 + loadTrending 호출 */
  function clearTopic(): void {
    state.topic = null;
    markActiveTopic(null);
    topicHeader.classList.add('hidden');
    trendBar.classList.remove('hidden');
    void loadTrending();
  }

  /** 토픽 뷰의 플랫폼 탭 활성 상태를 동기화한다. */
  /** 입력: 없음 / 출력: 없음 / 결과: 탭 CSS 클래스 토글 */
  function syncTopicPlatformTabs(): void {
    topicPlatformTabs.querySelectorAll<HTMLButtonElement>('button').forEach((b) => {
      const active = b.dataset.tplatform === state.topicPlatform;
      b.classList.toggle('bg-slate-200/70', active);
      b.classList.toggle('dark:bg-white/[.08]', active);
      b.classList.toggle('text-slate-800', active);
      b.classList.toggle('dark:text-slate-200', active);
      b.classList.toggle('text-slate-500', !active);
      b.classList.toggle('dark:text-slate-400', !active);
    });
  }

  /** 현재 토픽/플랫폼/언어로 저장소 목록을 로드한다. */
  /** 입력: 없음 / 출력: Promise<void> / 결과: grid에 결과 렌더링 */
  async function loadTopicRepos(): Promise<void> {
    if (!state.topic) return;
    skeletons();
    try {
      const params = new URLSearchParams({
        topic: state.topic, platform: state.topicPlatform, lang: state.lang, limit: '10',
      });
      const res = await fetch(`/api/topic-repos?${params.toString()}`);
      const data = (await res.json()) as TrendingResponse;
      renderTopicRepos(data);
    } catch {
      grid.innerHTML = `<p class="col-span-full text-center text-red-500 py-10">${t('loadFail')}</p>`;
    }
  }

  topicBack.addEventListener('click', clearTopic);
  topicPlatformTabs.querySelectorAll<HTMLButtonElement>('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.topicPlatform = btn.dataset.tplatform ?? 'all';
      syncTopicPlatformTabs();
      void loadTopicRepos();
    });
  });

  const emptyTitle = document.getElementById('emptyTitle') as HTMLElement;
  const emptyDesc = document.getElementById('emptyDesc') as HTMLElement;

  /** 플랫폼별 수집 가능 날짜 목록을 로드해 셀렉트를 채운다. */
  /** 입력: 없음 / 출력: Promise<void> / 결과: dateSelect 옵션 + state.date 갱신 */
  async function loadDates(): Promise<void> {
    try {
      const res = await fetch(`/api/dates?platform=${state.platform}`);
      const data = (await res.json()) as { dates?: string[] };
      const dates = data.dates ?? [];
      dateSelect.innerHTML = dates.length
        ? dates.map((d) => `<option value="${d}">${d}</option>`).join('')
        : '<option value="">—</option>';
      if (dates.length) {
        state.date = dates[0];
        dateSelect.value = state.date;
      }
    } catch {
      /* 날짜 목록 실패는 무시 */
    }
  }

  /** 현재 플랫폼/언어/날짜의 트렌딩 목록을 로드·렌더링한다. */
  /** 입력: 없음 / 출력: Promise<void> / 결과: grid DOM 갱신 */
  async function loadTrending(): Promise<void> {
    skeletons();
    try {
      const params = new URLSearchParams({ platform: state.platform, lang: state.lang });
      if (state.date) params.set('date', state.date);
      const res = await fetch(`/api/trending?${params.toString()}`);
      const data = (await res.json()) as TrendingResponse;
      state.lastItems = data.items ?? [];
      if (!state.lastItems.length) {
        grid.innerHTML = '';
        emptyTitle.textContent = t('emptyTitle');
        emptyDesc.textContent = t('emptyDesc');
        empty.classList.remove('hidden');
        return;
      }
      renderFiltered();
      updatedAt.textContent = `${t('updated')} ${new Date().toLocaleString('ko-KR')}`;
    } catch {
      grid.innerHTML = `<p class="col-span-full text-center text-red-500 py-10">${t('loadFail')}</p>`;
    }
  }

  /** 주간/월간 집계 랭킹을 로드·렌더링한다. */
  /** 입력: 없음 / 출력: Promise<void> / 결과: grid DOM 갱신 */
  async function loadRanking(): Promise<void> {
    skeletons();
    try {
      const params = new URLSearchParams({
        period: state.period === 'week' ? 'week' : 'month',
        platform: state.platform === 'all' ? 'all' : state.platform,
        lang: state.lang,
      });
      const res = await fetch(`/api/ranking?${params.toString()}`);
      const data = (await res.json()) as TrendingResponse;
      state.lastItems = data.items ?? [];
      if (!state.lastItems.length) {
        grid.innerHTML = '';
        emptyTitle.textContent = t('emptyTitle');
        emptyDesc.textContent = t('emptyDesc');
        empty.classList.remove('hidden');
        return;
      }
      renderFiltered();
      updatedAt.textContent = `${t('updated')} ${new Date().toLocaleString('ko-KR')}`;
    } catch {
      grid.innerHTML = `<p class="col-span-full text-center text-red-500 py-10">${t('loadFail')}</p>`;
    }
  }

  // ---- 저장소 상세 뷰 ----
  let currentRepo = '';

  /** 현재 URL 경로에서 /repo/{full_name}을 추출한다. */
  /** 입력: 없음 / 출력: string — full_name 또는 빈 문자열 / 결과: 없음 */
  function repoFromPath(): string {
    const m = location.pathname.match(/^\/repo\/(.+)$/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  /** 저장소 상세를 API에서 가져와 repoView에 렌더링한다. */
  /** 입력: 없음 / 출력: Promise<void> / 결과: repoView DOM 갱신 */
  async function loadRepoDetail(): Promise<void> {
    currentRepo = repoFromPath();
    if (!currentRepo) {
      state.view = 'list';
      repoView.classList.add('hidden');
      grid.classList.remove('hidden');
      return;
    }
    state.view = 'repo';
    grid.classList.add('hidden');
    empty.classList.add('hidden');
    topicHeader.classList.add('hidden');
    repoView.classList.remove('hidden');
    repoView.innerHTML = '<div class="skeleton h-8 w-1/2 mb-4"></div><div class="skeleton h-4 w-full mb-2"></div><div class="skeleton h-4 w-5/6"></div>';
    try {
      const res = await fetch(`/api/repo/${encodeURIComponent(currentRepo)}?lang=${state.lang}`);
      if (!res.ok) throw new Error('not found');
      const data = (await res.json()) as { item: TrendingItem };
      const it = data.item;
      const badgeMeta = `
        <div class="flex items-center gap-2 flex-wrap text-xs text-slate-500 dark:text-slate-400">
          ${it.snapshot_platform ? `<span class="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-white/[.05] border border-slate-200 dark:border-white/[.07] font-medium">${escapeHtml(it.snapshot_platform)}</span>` : ''}
          ${it.collected_date ? `<span>${t('detailCollected')} ${escapeHtml(it.collected_date)}</span>` : ''}
          ${it.taxonomy ? `<span class="px-2 py-0.5 rounded-md bg-indigo-100 dark:bg-indigo-400/15 border border-indigo-300 dark:border-indigo-400/30 text-indigo-700 dark:text-indigo-300 font-semibold">${escapeHtml(it.taxonomy)}</span>` : ''}
          ${it.language ? `<span class="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-white/[.05] border border-slate-200 dark:border-white/[.07] font-medium">${escapeHtml(it.language)}</span>` : ''}
          <span class="inline-flex items-center gap-1">${ICON.star}<span class="font-medium">${fmtStars(it.stars)}</span></span>
          ${it.license ? `<span class="px-2 py-0.5 rounded-md font-bold text-[10px] bg-amber-100 dark:bg-amber-400/15 border border-amber-300 dark:border-amber-400/30 text-amber-800 dark:text-amber-300">${escapeHtml(licenseShort(it.license))}</span>` : `<span class="px-2 py-0.5 rounded-md text-[10px] bg-slate-100 dark:bg-white/[.04] border border-slate-200 dark:border-white/[.07] text-slate-400">${t('noLicense')}</span>`}
        </div>`;
      const summaryLangs = (it.summaries ?? {});
      const langBtns = Object.keys(summaryLangs).map((lg) => {
        const label = lg === 'ko' ? '한국어' : lg === 'en' ? 'English' : '中文';
        return `<button class="sum-lang-btn px-3 py-1.5 rounded-md text-xs font-semibold ${lg === state.lang ? 'bg-slate-200 dark:bg-white/[.1] text-slate-800 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}" data-lang="${lg}">${label}</button>`;
      }).join('');
      const summaryHtml = (lg: string) => `
        <div class="sum-pane ${lg === state.lang ? '' : 'hidden'}" data-pane="${lg}">
          <ul class="text-sm leading-relaxed text-slate-600 dark:text-slate-300 space-y-2">
            ${(summaryLangs[lg] ?? []).map((l) => `<li class="flex gap-2"><span class="mt-[7px] w-1 h-1 rounded-full bg-slate-400/70 shrink-0"></span><span>${escapeHtml(l)}</span></li>`).join('')}
          </ul>
        </div>`;
      const readme = it.readme_excerpt
        ? `<details class="mt-5"><summary class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-500 cursor-pointer hover:text-slate-700 dark:hover:text-slate-300">${t('detailReadme')}</summary><pre class="mt-2 text-xs whitespace-pre-wrap leading-relaxed text-slate-600 dark:text-slate-400 bg-white/[.03] dark:bg-white/[.02] border border-slate-200 dark:border-white/[.06] rounded-xl p-4 max-h-80 overflow-y-auto">${escapeHtml(it.readme_excerpt)}</pre></details>`
        : '';
      const related = (it.related_topics ?? []).length
        ? `<div class="mt-5"><h3 class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-500 mb-2">${t('detailRelated')}</h3><div class="flex gap-1.5 flex-wrap">${it.related_topics!.map((tp) => `<button class="rel-topic px-2.5 py-1 rounded-full text-[11px] font-medium bg-white/[.04] border border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 hover:border-[#d97757]/50 hover:text-[#d97757] transition-colors" data-topic="${escapeHtml(tp)}">#${escapeHtml(tp)}</button>`).join('')}</div></div>`
        : '';
      repoView.innerHTML = `
        <button id="repoBack" class="text-xs text-slate-500 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 mb-3 inline-flex items-center gap-1 transition-colors">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          ${t('backToTrending')}
        </button>
        <article class="card rounded-2xl p-6 fade-up">
          <div class="flex items-start gap-3">
            <div class="min-w-0 flex-1">
              <a href="${escapeHtml(it.repo_url)}" target="_blank" rel="noopener" class="font-bold text-xl text-slate-800 dark:text-slate-100 hover:text-blue-500 dark:hover:text-blue-400 underline-offset-4 hover:underline">${escapeHtml(it.repo_full_name)}</a>
              ${it.description ? `<p class="text-sm text-slate-600 dark:text-slate-400 mt-1.5 leading-relaxed">${escapeHtml(it.description)}</p>` : ''}
              <div class="mt-3">${badgeMeta}</div>
            </div>
            <a href="${escapeHtml(it.repo_url)}" target="_blank" rel="noopener" class="shrink-0 inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-white/[.06] border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-white/[.12] transition-colors">GitHub ${ICON.arrow}</a>
          </div>
          <div class="mt-5">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-500">${t('detailSummary')}</h3>
              <div class="flex gap-1">${langBtns}</div>
            </div>
            ${Object.keys(summaryLangs).map(summaryHtml).join('')}
          </div>
          ${readme}
          ${related}
        </article>`;
      document.getElementById('repoBack')?.addEventListener('click', () => {
        location.href = '/';
      });
      repoView.querySelectorAll<HTMLButtonElement>('.sum-lang-btn').forEach((b) => {
        b.addEventListener('click', () => {
          const lg = b.dataset.lang ?? state.lang;
          repoView.querySelectorAll('.sum-pane').forEach((p) =>
            p.classList.toggle('hidden', (p as HTMLElement).dataset.pane !== lg));
          repoView.querySelectorAll('.sum-lang-btn').forEach((x) => {
            const on = x === b;
            x.className = `sum-lang-btn px-3 py-1.5 rounded-md text-xs font-semibold ${on ? 'bg-slate-200 dark:bg-white/[.1] text-slate-800 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}`;
          });
        });
      });
      repoView.querySelectorAll<HTMLButtonElement>('.rel-topic').forEach((b) => {
        b.addEventListener('click', () => {
          const tp = b.dataset.topic ?? '';
          const cnt = allTopics.find((x) => x.topic === tp)?.count ?? 0;
          selectTopic(tp, cnt);
          state.view = 'list';
          repoView.classList.add('hidden');
          grid.classList.remove('hidden');
          topicHeader.classList.remove('hidden');
        });
      });
    } catch {
      repoView.innerHTML = `<p class="text-center text-red-500 py-10">${t('detailNotFound')}</p>`;
    }
  }

  syncTopicPlatformTabs();
  applyI18n();
  minStarsLabel.textContent = fmtStars(state.minStars);

  /** URL 경로에 따라 목록/상세 뷰를 초기화한다. */
  /** 입력: 없음 / 출력: 없음 / 결과: 적절한 뷰 로드 트리거 */
  function route(): void {
    if (repoFromPath()) {
      void loadRepoDetail();
      return;
    }
    state.view = 'list';
    repoView.classList.add('hidden');
    grid.classList.remove('hidden');
    topicHeader.classList.remove('hidden');
    void loadTopics();
    void loadDates().then(() => {
      if (state.period === 'daily') void loadTrending();
      else void loadRanking();
    });
  }
  window.addEventListener('popstate', route);
  route();
})();
