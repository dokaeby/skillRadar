"use strict";
/* SkillRadar 프론트엔드: 탭/언어/날짜 전환 + 카드 렌더링 */
(() => {
    const state = {
        platform: 'claude',
        lang: 'ko',
        date: '',
        dates: [],
        topic: null,
        topicPlatform: 'all',
        topicCount: 0,
    };
    const grid = document.getElementById('grid');
    const empty = document.getElementById('empty');
    const dateSelect = document.getElementById('dateSelect');
    const updatedAt = document.getElementById('updatedAt');
    const themeToggle = document.getElementById('themeToggle');
    const themeIconSun = document.getElementById('themeIcon');
    const themeIconMoon = document.getElementById('themeIconMoon');
    const langToggle = document.getElementById('langToggle');
    const platformTabs = document.getElementById('platformTabs');
    const trendBar = document.getElementById('trendBar');
    const topicList = document.getElementById('topicList');
    const topicHeader = document.getElementById('topicHeader');
    const relatedTopics = document.getElementById('relatedTopics');
    let allTopics = [];
    const topicTitle = document.getElementById('topicTitle');
    const topicCount = document.getElementById('topicCount');
    const topicBack = document.getElementById('topicBack');
    const topicPlatformTabs = document.getElementById('topicPlatformTabs');
    const ICON = {
        star: '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.2 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8z"/></svg>',
        trending: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg>',
        arrow: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7M9 7h8v8"/></svg>',
    };
    function syncThemeIcon() {
        const dark = isDark();
        themeIconSun.classList.toggle('hidden', dark);
        themeIconMoon.classList.toggle('hidden', !dark);
    }
    // 다크모드 초기화 (localStorage 우선)
    const savedTheme = localStorage.getItem('sr-theme');
    if (savedTheme === 'light')
        document.documentElement.classList.remove('dark');
    if (savedTheme === 'dark')
        document.documentElement.classList.add('dark');
    const isDark = () => document.documentElement.classList.contains('dark');
    syncThemeIcon();
    themeToggle.addEventListener('click', () => {
        const dark = document.documentElement.classList.toggle('dark');
        localStorage.setItem('sr-theme', dark ? 'dark' : 'light');
        syncThemeIcon();
    });
    function setActiveLang(btn) {
        document.querySelectorAll('#langToggle button').forEach((b) => {
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
    langToggle.querySelectorAll('button').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.lang = btn.dataset.lang ?? 'ko';
            setActiveLang(btn);
            void loadTrending();
        });
    });
    platformTabs.querySelectorAll('button').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.platform = btn.dataset.platform ?? 'claude';
            platformTabs.querySelectorAll('button').forEach((b) => b.classList.toggle('tab-active', b === btn));
            void loadDates();
            void loadTrending();
        });
    });
    dateSelect.addEventListener('change', () => {
        state.date = dateSelect.value;
        void loadTrending();
    });
    function skeletons() {
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
    function fmtStars(n) {
        if (n >= 1000)
            return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
        return String(n);
    }
    function licenseShort(license) {
        const map = {
            'Apache-2.0': 'Apache-2.0', 'MIT': 'MIT', 'BSD-2-Clause': 'BSD-2',
            'BSD-3-Clause': 'BSD-3', 'GPL-3.0': 'GPL-3', 'GPL-2.0': 'GPL-2',
            'AGPL-3.0': 'AGPL-3', 'LGPL-3.0': 'LGPL-3', 'MPL-2.0': 'MPL-2.0',
            'ISC': 'ISC', 'Unlicense': 'Unlicense', '0BSD': '0BSD',
            'CC0-1.0': 'CC0', 'EPL-2.0': 'EPL-2', 'BSL-1.0': 'BSL',
            'Elastic-2.0': 'Elastic-2', 'MS-PL': 'MS-PL', 'Zlib': 'Zlib',
            'WTFPL': 'WTFPL', 'Python-2.0': 'PSF', 'Artistic-2.0': 'Artistic',
        };
        if (map[license])
            return map[license];
        const m = license.match(/^GPL-(\d+\.0)/);
        if (m)
            return `GPL-${m[1]}`;
        const b = license.match(/^BSD-(\d)-Clause/);
        if (b)
            return `BSD-${b[1]}`;
        return license.length > 12 ? license.slice(0, 12) : license;
    }
    function escapeHtml(s) {
        const map = {
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        };
        return String(s ?? '').replace(/[&<>"']/g, (c) => map[c]);
    }
    function renderCard(item) {
        const topics = (item.topics || []).slice(0, 4)
            .map((t) => `<span class="topic-chip text-[10px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-white/[.05] border border-slate-200 dark:border-white/[.07] text-slate-600 dark:text-slate-400">${escapeHtml(t)}</span>`)
            .join('');
        const delta = item.stars_today;
        const deltaInner = delta === null || delta === undefined
            ? '<span class="text-slate-500 dark:text-slate-500">—</span>'
            : delta > 0
                ? `<span class="text-emerald-400 font-semibold inline-flex items-center gap-1">${ICON.trending}+${fmtStars(delta)}</span>`
                : '<span class="text-slate-500 dark:text-slate-500">±0</span>';
        const lines = (item.summary || []).map((l) => `<li class="flex gap-2.5"><span class="mt-[7px] w-1 h-1 rounded-full bg-slate-400/70 dark:bg-slate-500/60 shrink-0"></span><span class="line-clamp-3">${escapeHtml(l)}</span></li>`).join('');
        const description = item.description
            ? `<p class="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 leading-relaxed mt-1">${escapeHtml(item.description)}</p>`
            : '';
        return `
    <article class="card fade-up rounded-2xl p-5 flex flex-col gap-3.5">
      <div class="flex items-start gap-3">
        <span class="rank-badge shrink-0 w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm text-slate-700 dark:text-slate-200">${item.rank}</span>
        <div class="min-w-0 flex-1">
          <a href="${item.repo_url}" target="_blank" rel="noopener"
             class="font-semibold text-[15px] leading-snug text-slate-800 dark:text-slate-100 hover:text-blue-500 dark:hover:text-blue-400 underline-offset-4 decoration-slate-400/50 hover:underline truncate block transition-colors">
            ${escapeHtml(item.repo_full_name)}
          </a>
          ${description}
          ${item.platform ? `<span class="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide ${PLATFORM_BADGE[item.platform] ?? 'text-slate-500'}"><span class="w-1.5 h-1.5 rounded-full ${PLATFORM_DOT[item.platform] ?? 'bg-slate-500'}"></span>${item.platform}</span>` : ''}
          <div class="flex items-center gap-3 mt-2 text-xs text-slate-600 dark:text-slate-400 flex-wrap">
            ${item.license ? `<span class="px-2 py-0.5 rounded-md font-bold text-[10px] tracking-wide bg-amber-100 dark:bg-amber-400/15 border border-amber-300 dark:border-amber-400/30 text-amber-800 dark:text-amber-300" title="License: ${escapeHtml(item.license)}">${escapeHtml(licenseShort(item.license))}</span>` : ''}
            ${item.language ? `<span class="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-white/[.05] border border-slate-200 dark:border-white/[.07] font-medium text-slate-700 dark:text-slate-200">${escapeHtml(item.language)}</span>` : ''}
            <span class="inline-flex items-center gap-1">${ICON.star}<span class="font-medium text-slate-600 dark:text-slate-300">${fmtStars(item.stars)}</span></span>
            <span class="inline-flex items-center gap-1">오늘 ${deltaInner}</span>
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
    const PLATFORM_BADGE = {
        claude: 'text-[#b4552d] dark:text-claude', chatgpt: 'text-[#0b7a5c] dark:text-chatgpt', gemini: 'text-[#2b63d9] dark:text-gemini',
    };
    const PLATFORM_DOT = {
        claude: 'bg-claude', chatgpt: 'bg-chatgpt', gemini: 'bg-gemini',
    };
    function renderTopicRepos(data) {
        if (!data.items || !data.items.length) {
            grid.innerHTML = '';
            emptyTitle.textContent = '이 주제의 저장소가 없습니다';
            emptyDesc.textContent = '다른 주제를 선택하거나 트렌딩으로 돌아가세요.';
            empty.classList.remove('hidden');
            return;
        }
        empty.classList.add('hidden');
        grid.innerHTML = data.items
            .map((item, i) => renderCard({ ...item, rank: i + 1 }))
            .join('');
        updatedAt.textContent = '';
    }
    async function loadTopics() {
        try {
            const res = await fetch('/api/topics');
            const data = (await res.json());
            const topics = data.topics ?? [];
            allTopics = topics;
            if (!topics.length) {
                topicList.innerHTML = '<p class="text-xs text-slate-500 px-2 py-3">주제 데이터가 없습니다</p>';
                return;
            }
            topicList.innerHTML = topics.map((t) => `
        <button class="topic-btn shrink-0 lg:w-full text-left px-3 py-2 rounded-lg text-[13px] font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/[.05] dark:hover:bg-white/[.05] hover:text-slate-800 dark:hover:text-slate-200 transition-colors flex items-center justify-between gap-2"
                data-topic="${escapeHtml(t.topic)}">
          <span class="truncate"># ${escapeHtml(t.topic)}</span>
          <span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 dark:bg-white/[.05] border border-slate-200 dark:border-white/[.08] text-slate-600 dark:text-slate-500">${t.count}</span>
        </button>`).join('');
            topicList.querySelectorAll('.topic-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const topic = btn.dataset.topic ?? '';
                    const count = Number(btn.querySelector('span:last-child')?.textContent ?? 0);
                    selectTopic(topic, count);
                });
            });
        }
        catch {
            topicList.innerHTML = '<p class="text-xs text-slate-500 px-2 py-3">주제를 불러오지 못했습니다</p>';
        }
    }
    function markActiveTopic(topic) {
        topicList.querySelectorAll('.topic-btn').forEach((b) => {
            const active = b.dataset.topic === topic;
            b.classList.toggle('bg-slate-200/70', active);
            b.classList.toggle('dark:bg-white/[.07]', active);
            b.classList.toggle('text-slate-800', active);
            b.classList.toggle('dark:text-slate-200', active);
            b.classList.toggle('text-slate-500', !active);
            b.classList.toggle('dark:text-slate-400', !active);
        });
    }
    function selectTopic(topic, count) {
        state.topic = topic;
        state.topicPlatform = 'all';
        markActiveTopic(topic);
        topicTitle.textContent = `#${topic}`;
        topicCount.textContent = `최근 30일 ${count}개 저장소`;
        topicHeader.classList.remove('hidden');
        trendBar.classList.add('hidden');
        syncTopicPlatformTabs();
        void loadTopicRepos();
        void loadRelatedTopics(topic);
    }
    async function loadRelatedTopics(topic) {
        relatedTopics.innerHTML = '';
        try {
            const res = await fetch(`/api/related-topics?topic=${encodeURIComponent(topic)}`);
            const data = (await res.json());
            const related = (data.related ?? []).filter((r) => r.topic !== topic).slice(0, 8);
            if (!related.length)
                return;
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
        }
        catch {
            /* 관련 주제 실패는 무시 */
        }
    }
    function clearTopic() {
        state.topic = null;
        markActiveTopic(null);
        topicHeader.classList.add('hidden');
        trendBar.classList.remove('hidden');
        void loadTrending();
    }
    function syncTopicPlatformTabs() {
        topicPlatformTabs.querySelectorAll('button').forEach((b) => {
            const active = b.dataset.tplatform === state.topicPlatform;
            b.classList.toggle('bg-slate-200/70', active);
            b.classList.toggle('dark:bg-white/[.08]', active);
            b.classList.toggle('text-slate-800', active);
            b.classList.toggle('dark:text-slate-200', active);
            b.classList.toggle('text-slate-500', !active);
            b.classList.toggle('dark:text-slate-400', !active);
        });
    }
    async function loadTopicRepos() {
        if (!state.topic)
            return;
        skeletons();
        try {
            const params = new URLSearchParams({
                topic: state.topic, platform: state.topicPlatform, lang: state.lang, limit: '10',
            });
            const res = await fetch(`/api/topic-repos?${params.toString()}`);
            const data = (await res.json());
            renderTopicRepos(data);
        }
        catch {
            grid.innerHTML = '<p class="col-span-full text-center text-red-500 py-10">데이터를 불러오지 못했습니다.</p>';
        }
    }
    topicBack.addEventListener('click', clearTopic);
    topicPlatformTabs.querySelectorAll('button').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.topicPlatform = btn.dataset.tplatform ?? 'all';
            syncTopicPlatformTabs();
            void loadTopicRepos();
        });
    });
    const emptyTitle = document.getElementById('emptyTitle');
    const emptyDesc = document.getElementById('emptyDesc');
    async function loadDates() {
        try {
            const res = await fetch(`/api/dates?platform=${state.platform}`);
            const data = (await res.json());
            state.dates = data.dates ?? [];
            dateSelect.innerHTML = state.dates.length
                ? state.dates.map((d) => `<option value="${d}">${d}</option>`).join('')
                : '<option value="">—</option>';
            if (state.dates.length) {
                state.date = state.dates[0];
                dateSelect.value = state.date;
            }
        }
        catch {
            /* 날짜 목록 실패는 무시 */
        }
    }
    async function loadTrending() {
        skeletons();
        try {
            const params = new URLSearchParams({ platform: state.platform, lang: state.lang });
            if (state.date)
                params.set('date', state.date);
            const res = await fetch(`/api/trending?${params.toString()}`);
            const data = (await res.json());
            if (!data.items || !data.items.length) {
                grid.innerHTML = '';
                empty.classList.remove('hidden');
                return;
            }
            empty.classList.add('hidden');
            grid.innerHTML = data.items.map(renderCard).join('');
            updatedAt.textContent = `업데이트 ${new Date().toLocaleString('ko-KR')}`;
        }
        catch {
            grid.innerHTML = '<p class="col-span-full text-center text-red-500 py-10">데이터를 불러오지 못했습니다.</p>';
        }
    }
    syncTopicPlatformTabs();
    void loadTopics();
    void loadDates().then(loadTrending);
})();
