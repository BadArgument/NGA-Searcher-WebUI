/* === NGA 搜索器 WebUI 脚本 === */

// ========== 全局状态 ==========
const state = {
  isOnline: true,          // 默认在线搜索
  filterGroups: [[]],      // 筛选组：[[{type,value,label,dateFrom,dateTo}], ...]
  searchOffset: 0,
  searchHasMore: true,
  searchLoading: false,
  lastSearchParams: null,
  page: null,              // 当前页面标识
  scrollObserver: null,    // 无限滚动 observer
};

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
  state.page = document.body.dataset.page || null;
  initNav();
  if (state.page === 'search') initSearchPage();
  if (state.page === 'favorites') initFavoritesPage();
  if (state.page === 'boards') initBoardsPage();
});

// ========== 导航 ==========
function initNav() {
  // 高亮当前页面导航项
  const active = state.page;
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.toggle('active', link.dataset.page === active);
  });
}

// ========== Toast 通知 ==========
function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.remove(); }, 2000);
}

// ========== 工具函数 ==========
function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0') + ' ' +
    String(d.getHours()).padStart(2, '0') + ':' +
    String(d.getMinutes()).padStart(2, '0');
}

// ========== 搜索页 ==========
function initSearchPage() {
  const searchBtn = document.getElementById('search-btn');
  const toggleTrack = document.getElementById('toggle-track');
  const toggleGroup = document.getElementById('toggle-group');
  const sortSelect = document.getElementById('sort-select');

  // 在线/离线切换（默认在线）
  state.isOnline = true;
  toggleTrack.classList.add('on');

  toggleGroup.addEventListener('click', () => {
    state.isOnline = !state.isOnline;
    toggleTrack.classList.toggle('on', state.isOnline);
  });

  // 搜索
  searchBtn.addEventListener('click', () => { state.searchOffset = 0; state.searchHasMore = true; doSearch(true); });

  // 初始化筛选组
  const filterGroupsContainer = document.getElementById('filter-groups');
  let activeGroupIdx = 0;

  function renderAllGroups() {
    filterGroupsContainer.innerHTML = '';
    state.filterGroups.forEach((filters, gi) => {
      const groupEl = document.createElement('div');
      groupEl.className = 'filter-group';
      groupEl.innerHTML =
        '<div class="filter-group-bar">' +
        '<span class="filter-group-label" data-gi="' + gi + '">组 ' + (gi + 1) + (gi === activeGroupIdx ? ' ●' : '') + '</span>' +
        (state.filterGroups.length > 1 ? '<button class="btn btn-sm filter-group-remove" data-gi="' + gi + '"><i class="fa-solid fa-xmark"></i></button>' : '') +
        '</div>' +
        '<div class="filter-chips" data-gi="' + gi + '"></div>' +
        '<div class="filter-add-row" data-gi="' + gi + '">' +
        '<div class="cmd-input-wrap">' +
        '<input type="text" class="cmd-input" placeholder="筛选...（author: board: topic: reply: after: before: not: 或直接输入关键词）" autocomplete="off">' +
        '<div class="cmd-dropdown"></div>' +
        '</div>' +
        '</div>';
      filterGroupsContainer.appendChild(groupEl);
    });

    // 绑定组标签点击
    filterGroupsContainer.querySelectorAll('.filter-group-label').forEach(el => {
      el.addEventListener('click', () => { activeGroupIdx = parseInt(el.dataset.gi); renderAllGroups(); });
    });

    // 绑定删除组
    filterGroupsContainer.querySelectorAll('.filter-group-remove').forEach(el => {
      el.addEventListener('click', () => {
        const gi = parseInt(el.dataset.gi);
        state.filterGroups.splice(gi, 1);
        if (activeGroupIdx >= state.filterGroups.length) activeGroupIdx = state.filterGroups.length - 1;
        renderAllGroups();
      });
    });

    // 渲染 chips
    const names = { fid: '版面', author: '作者', date: '时间', exclude: '排除', match: '匹配', search_mode: '模式' };
    state.filterGroups.forEach((filters, gi) => {
      const chipsEl = filterGroupsContainer.querySelector('.filter-chips[data-gi="' + gi + '"]');
      filters.forEach((f, fi) => {
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.innerHTML = names[f.type] + ': ' + escapeHtml(f.label) +
          ' <span class="chip-remove" data-gi="' + gi + '" data-fi="' + fi + '"><i class="fa-solid fa-xmark"></i></span>';
        chipsEl.appendChild(chip);
      });
    });

    // 绑定 chip 移除
    filterGroupsContainer.querySelectorAll('.chip-remove').forEach(el => {
      el.addEventListener('click', () => {
        state.filterGroups[parseInt(el.dataset.gi)].splice(parseInt(el.dataset.fi), 1);
        renderAllGroups();
      });
    });

    // 初始化命令面板
    state.filterGroups.forEach((filters, gi) => {
      const row = filterGroupsContainer.querySelector('.filter-add-row[data-gi="' + gi + '"]');
      if (row) initCmdPalette(row, gi);
    });
  }

  // ========== 命令面板 ==========
  const CMD_PREFIXES = [
    { prefix: 'author:', desc: '作者', type: 'author', icon: 'fa-user' },
    { prefix: 'board:', desc: '版面', type: 'fid', icon: 'fa-layer-group' },
    { prefix: 'after:', desc: '起始时间', type: 'date_from', icon: 'fa-calendar' },
    { prefix: 'before:', desc: '截止时间', type: 'date_to', icon: 'fa-calendar' },
    { prefix: 'not:', desc: '排除关键词', type: 'exclude', icon: 'fa-ban' },
    { prefix: 'topic:', desc: '主题模式', type: 'search_mode', mode: 'thread', icon: 'fa-file-lines' },
    { prefix: 'reply:', desc: '回复模式', type: 'search_mode', mode: 'post', icon: 'fa-comments' },
  ];

  function detectPrefix(val) {
    var lower = val.toLowerCase();
    for (var i = 0; i < CMD_PREFIXES.length; i++) {
      if (lower.startsWith(CMD_PREFIXES[i].prefix)) return CMD_PREFIXES[i];
    }
    return null;
  }

  function initCmdPalette(row, gi) {
    var input = row.querySelector('.cmd-input');
    var dropdown = row.querySelector('.cmd-dropdown');
    var cmdState = 'idle', activeIdx = -1, timer = null;
    var dateType = '';

    function reset() {
      cmdState = 'idle'; activeIdx = -1; input.value = '';
      dropdown.classList.remove('open'); dropdown.innerHTML = '';
      dateType = '';
    }

    function addChip(type, label, value, dateFrom, dateTo) {
      state.filterGroups[gi].push({ type: type, value: value, label: label, dateFrom: dateFrom || '', dateTo: dateTo || '' });
      renderAllGroups();
    }

    function showDropdown(html) {
      dropdown.innerHTML = html;
      dropdown.classList.add('open');
    }

    // ---------- 前缀补全 UI ----------

    function showPrefixHints(filter) {
      cmdState = 'prefix';
      var lower = (filter || '').toLowerCase();
      var matches = CMD_PREFIXES.filter(function(p) { return p.prefix.startsWith(lower); });
      if (!matches.length) { dropdown.classList.remove('open'); return; }
      showDropdown(matches.map(function(p, i) {
        return '<div class="cmd-opt' + (i === activeIdx ? ' active' : '') + '" data-idx="' + i + '"><i class="fa-solid ' + p.icon + '"></i> <strong>' + p.prefix + '</strong><span class="hint">' + p.desc + '</span></div>';
      }).join(''));
      dropdown.querySelectorAll('.cmd-opt').forEach(function(el) {
        el.addEventListener('mousedown', function(e) {
          e.preventDefault();
          var idx = parseInt(el.dataset.idx);
          if (matches[idx]) applyPrefix(matches[idx]);
        });
      });
    }

    function applyPrefix(p) {
      input.value = p.prefix;
      input.focus();
      switch (p.type) {
        case 'fid': cmdState = 'board'; showBoardSearch(''); break;
        case 'author': cmdState = 'author'; showAuthorSearch(''); break;
        case 'date_from': dateType = 'after'; cmdState = 'date'; showDatePicker(); break;
        case 'date_to': dateType = 'before'; cmdState = 'date'; showDatePicker(); break;
        case 'exclude': cmdState = 'exclude'; showExcludeHint(); break;
        case 'search_mode': cmdState = 'mode'; showModeHint(p); break;
      }
    }

    function showBoardSearch(query) {
      if (!query) {
        showDropdown('<div class="cmd-opt" style="color:var(--muted);"><i class="fa-solid fa-layer-group"></i> 输入版面名称搜索...</div>');
        return;
      }
      clearTimeout(timer);
      timer = setTimeout(async function() {
        try {
          var res = await fetch('/api/boards?q=' + encodeURIComponent(query));
          var boards = await res.json();
          activeIdx = -1;
          var html = boards.slice(0, 10).map(function(b, i) {
            return '<div class="cmd-opt" data-fid="' + b.fid + '" data-name="' + escapeHtml(b.name) + '"><i class="fa-solid fa-layer-group"></i> ' + escapeHtml(b.name) + ' <span class="hint">fid=' + b.fid + '</span></div>';
          }).join('') || '<div class="cmd-opt" style="color:var(--muted);">无匹配版面</div>';
          showDropdown(html);
          dropdown.querySelectorAll('.cmd-opt[data-fid]').forEach(function(el) {
            el.addEventListener('mousedown', function(e) {
              e.preventDefault();
              addChip('fid', el.dataset.name, parseInt(el.dataset.fid));
              reset();
            });
          });
        } catch (_) {}
      }, 250);
    }

    function showAuthorSearch(query) {
      if (!query) {
        showDropdown('<div class="cmd-opt" style="color:var(--muted);"><i class="fa-solid fa-user"></i> 输入用户名搜索...</div>');
        return;
      }
      clearTimeout(timer);
      timer = setTimeout(async function() {
        try {
          var res = await fetch('/api/users/search?q=' + encodeURIComponent(query) + '&limit=10');
          var users = await res.json();
          activeIdx = -1;
          var html = users.map(function(u, i) {
            return '<div class="cmd-opt" data-uid="' + u.uid + '" data-name="' + escapeHtml(u.username) + '"><i class="fa-solid fa-user"></i> ' + escapeHtml(u.username) + ' <span class="hint">uid:' + u.uid + '</span></div>';
          }).join('') || '<div class="cmd-opt" style="color:var(--muted);">无匹配用户</div>';
          showDropdown(html);
          dropdown.querySelectorAll('.cmd-opt[data-uid]').forEach(function(el) {
            el.addEventListener('mousedown', function(e) {
              e.preventDefault();
              addChip('author', el.dataset.name, parseInt(el.dataset.uid));
              reset();
            });
          });
        } catch (_) {}
      }, 250);
    }

    function showDatePicker() {
      var label = dateType === 'after' ? '起始时间' : '截止时间';
      showDropdown('<div class="cmd-opt" style="padding:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;cursor:default;"><span style="font-size:13px;white-space:nowrap;">' + label + ':</span><input type="date" class="date-picker-val" style="flex:1;min-width:120px;padding:4px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px;"><button class="btn btn-primary btn-sm date-confirm-btn">确认</button></div>');
      var dateInp = dropdown.querySelector('.date-picker-val');
      var confirmBtn = dropdown.querySelector('.date-confirm-btn');
      dateInp.focus();
      var confirm = function() {
        var d = dateInp.value;
        if (!d) return;
        var df = dateType === 'after' ? d : '';
        var dt = dateType === 'before' ? d : '';
        var labelStr = dateType === 'after' ? '≥ ' + d : '≤ ' + d;
        addChip('date', labelStr, null, df, dt);
        reset();
      };
      confirmBtn.addEventListener('click', confirm);
      dateInp.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') confirm();
        if (e.key === 'Escape') reset();
      });
    }

    function showExcludeHint() {
      showDropdown('<div class="cmd-opt" style="color:var(--muted);"><i class="fa-solid fa-ban"></i> 输入排除关键词后按 Enter 确认</div>');
    }

    function showModeHint(p) {
      var label = p.mode === 'thread' ? '主题模式' : '回复模式';
      showDropdown('<div class="cmd-opt" style="color:var(--muted);"><i class="fa-solid ' + p.icon + '"></i> 按 Enter 确认: ' + label + '</div>');
    }

    // ---------- 事件绑定 ----------

    input.addEventListener('input', function() {
      var val = input.value;
      var prefix = detectPrefix(val);
      activeIdx = -1;  // 重置高亮，避免残留选中

      if (prefix) {
        // 已输入完整前缀，显示对应补全 UI
        var rest = val.substring(prefix.prefix.length).trim();
        switch (prefix.type) {
          case 'fid': cmdState = 'board'; showBoardSearch(rest); break;
          case 'author': cmdState = 'author'; showAuthorSearch(rest); break;
          case 'date_from': dateType = 'after'; cmdState = 'date'; showDatePicker(); break;
          case 'date_to': dateType = 'before'; cmdState = 'date'; showDatePicker(); break;
          case 'exclude': cmdState = 'exclude'; showExcludeHint(); break;
          case 'search_mode': cmdState = 'mode'; showModeHint(prefix); break;
        }
      } else {
        // 未匹配完整前缀，显示前缀提示
        showPrefixHints(val);
      }
    });

    input.addEventListener('keydown', function(e) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (cmdState === 'prefix' || cmdState === 'board' || cmdState === 'author') {
          var opts = dropdown.querySelectorAll('.cmd-opt');
          if (opts.length) {
            if (activeIdx >= 0) opts[activeIdx].classList.remove('active');
            activeIdx = activeIdx < opts.length - 1 ? activeIdx + 1 : 0;
            opts[activeIdx].classList.add('active');
          }
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (cmdState === 'prefix' || cmdState === 'board' || cmdState === 'author') {
          var opts = dropdown.querySelectorAll('.cmd-opt');
          if (opts.length) {
            if (activeIdx >= 0) opts[activeIdx].classList.remove('active');
            activeIdx = activeIdx > 0 ? activeIdx - 1 : opts.length - 1;
            opts[activeIdx].classList.add('active');
          }
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        var val = input.value.trim();
        var prefix = detectPrefix(val);

        if (cmdState === 'board' || cmdState === 'author') {
          // 选中当前高亮的搜索结果
          var active = dropdown.querySelector('.cmd-opt.active');
          if (active) {
            active.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
          }
        } else if (cmdState === 'prefix') {
          // 在前缀列表中，选中当前高亮项
          var active = dropdown.querySelector('.cmd-opt.active');
          if (active) {
            active.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
          } else if (val) {
            // 没有匹配前缀，当关键词添加
            addChip('match', val, val);
            reset();
          }
        } else if (cmdState === 'mode' && prefix) {
          // topic:/reply: 按 Enter 确认，同时提取关键词
          addChip('search_mode', prefix.mode === 'thread' ? '主题' : '回复', prefix.mode);
          var rest = val.substring(prefix.prefix.length).trim();
          if (rest) {
            addChip('match', rest, rest);
          }
          reset();
        } else if (prefix) {
          // 已输入前缀，处理对应逻辑
          var rest = val.substring(prefix.prefix.length).trim();
          if (prefix.type === 'exclude' && rest) {
            addChip('exclude', rest, rest);
            reset();
          }
          // board/author 通过点击下拉项添加，date 有自己的确认按钮
        } else if (val) {
          // 纯文本，当关键词添加
          addChip('match', val, val);
          reset();
        }
      } else if (e.key === 'Escape') {
        reset();
        input.blur();
      }
    });

    input.addEventListener('focus', function() {
      if (cmdState === 'idle') showPrefixHints('');
    });

    document.addEventListener('click', function(e) {
      if (!row.contains(e.target)) reset();
    });
  }

  renderAllGroups();

  // 添加筛选组
  document.getElementById('add-group-btn').addEventListener('click', () => {
    state.filterGroups.push([]);
    activeGroupIdx = state.filterGroups.length - 1;
    renderAllGroups();
  });

  // 刷新数据（重新抓取所有已索引版面并写入数据库）
  const refreshBtn = document.getElementById('refresh-data-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.disabled = true;
      refreshBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 刷新中...';
      try {
        const res = await fetch('/api/index/update', { method: 'POST' });
        const data = await res.json();
        showToast('已刷新 ' + (data ? data.boards_checked : 0) + ' 个版面');
        location.reload();
      } catch (e) {
        showToast('刷新失败: ' + e.message);
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> 刷新数据';
      }
    });
  }

  // 委托事件：点击结果卡片或收藏按钮
  const resultsArea = document.getElementById('results-area');
  resultsArea.addEventListener('click', (e) => {
    const favBtn = e.target.closest('.fav-btn');
    if (favBtn) {
      e.stopPropagation();
      const tid = parseInt(favBtn.dataset.tid);
      const subject = favBtn.dataset.subject;
      const author = favBtn.dataset.author;
      quickFav(tid, subject, author);
      return;
    }
    const item = e.target.closest('.waterfall-item');
    if (item && item.dataset.tid) {
      window.location.href = '/thread/' + item.dataset.tid;
    }
  });

  // 无限滚动
  const sentinel = document.getElementById('scroll-sentinel');
  if (sentinel) {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !state.searchLoading && state.searchHasMore) {
        loadMore();
      }
    }, { rootMargin: '300px' });
    observer.observe(sentinel);
  }
}

async function doSearch(reset) {
  for (const g of state.filterGroups) {
    if (!g.some(f => f.type === 'match')) {
      showToast('每组至少需要一个关键词（添加匹配关键词筛选）');
      return;
    }
  }

  if (reset) {
    state.searchOffset = 0;
    state.searchHasMore = true;
  }

  const params = {
    source: state.isOnline ? 'online' : 'offline',
    sort: document.getElementById('sort-select').value,
    limit: 20,
    offset: state.searchOffset,
  };

  const hasFilters = state.filterGroups.some(g => g.length > 0);
  if (hasFilters) {
    const groups = state.filterGroups.map(g => {
      const obj = {};
      g.forEach(f => {
        if (f.type === 'fid') obj.fid = f.value;
        if (f.type === 'author') obj.author = f.label;
        if (f.type === 'date') { if (f.dateFrom) obj.date_from = f.dateFrom; if (f.dateTo) obj.date_to = f.dateTo; }
        if (f.type === 'exclude') obj.exclude = f.value;
        if (f.type === 'match') obj.match = f.value;
        if (f.type === 'search_mode') obj.search_mode = f.value;
      });
      return obj;
    }).filter(g => Object.keys(g).length > 0);
    if (groups.length > 0) {
      params.groups = groups;
    }
  }

  state.lastSearchParams = params;
  state.searchLoading = true;

  try {
    const res = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    const data = await res.json();

    if (state.isOnline && reset && data.has_more) {
      await new Promise(r => setTimeout(r, 500));
    }

    const results = data.results || [];
    state.searchHasMore = data.has_more !== false;
    state.searchOffset += results.length;
    state.searchLoading = false;

    const r2 = await fetch('/api/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results: results }),
    });
    const html = await r2.text();
    renderResults(html, reset);
  } catch (e) {
    state.searchLoading = false;
    showToast('搜索失败: ' + e.message);
  }
}

function renderResults(html, reset) {
  const area = document.getElementById('results-area');
  if (reset) {
    if (!html.trim()) {
      area.innerHTML = '<div class="card"><div class="empty-state"><div class="empty-icon"><i class="fa-solid fa-inbox"></i></div><div class="empty-text">无结果</div></div></div>';
      return;
    }
    let wrapper = '<div class="waterfall" id="waterfall">' + html + '</div>';
    if (state.searchHasMore) {
      wrapper += '<div id="scroll-sentinel" style="height:60px;"><div class="bottom-loading"><i class="fa-solid fa-spinner fa-spin"></i> 加载更多...</div></div>';
    } else {
      wrapper += '<div class="bottom-loading" style="opacity:0.6;">— 已显示全部结果 —</div>';
    }
    area.innerHTML = wrapper;
  } else {
    const wf = document.getElementById('waterfall');
    if (!wf) return;
    wf.insertAdjacentHTML('beforeend', html);
    const sentinel = document.getElementById('scroll-sentinel');
    if (sentinel) {
      if (state.searchHasMore) {
        sentinel.innerHTML = '<div class="bottom-loading"><i class="fa-solid fa-spinner fa-spin"></i> 加载更多...</div>';
      } else {
        sentinel.innerHTML = '<div class="bottom-loading" style="opacity:0.6;">— 已显示全部结果 —</div>';
      }
    }
  }
  bindScrollSentinel();
}

function bindScrollSentinel() {
  if (state.scrollObserver) {
    state.scrollObserver.disconnect();
    state.scrollObserver = null;
  }
  const sentinel = document.getElementById('scroll-sentinel');
  if (!sentinel || !state.searchHasMore) return;
  state.scrollObserver = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !state.searchLoading && state.searchHasMore) {
      loadMore();
    }
  }, { rootMargin: '300px' });
  state.scrollObserver.observe(sentinel);
}

async function loadMore() {
  if (state.searchLoading || !state.searchHasMore || !state.lastSearchParams) return;

  state.searchLoading = true;
  state.lastSearchParams.offset = state.searchOffset;

  const sentinel = document.getElementById('scroll-sentinel');
  if (sentinel) sentinel.innerHTML = '<div class="bottom-loading"><i class="fa-solid fa-spinner fa-spin"></i> 加载更多...</div>';

  try {
    const res = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state.lastSearchParams),
    });
    const data = await res.json();
    const results = data.results || [];
    state.searchHasMore = data.has_more !== false;
    state.searchOffset += results.length;

    const r2 = await fetch('/api/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results: results }),
    });
    const html = await r2.text();
    state.searchLoading = false;
    renderResults(html, false);
  } catch (e) {
    state.searchLoading = false;
    if (sentinel) sentinel.innerHTML = '';
  }
}

// ========== 收藏 ==========
function initFavoritesPage() {
  // 收藏页的操作在全局函数中
}

async function quickFav(tid, subject, author) {
  try {
    await fetch('/api/favorites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tid, subject, author }),
    });
    showToast('已收藏');
  } catch (e) {
    showToast('收藏失败');
  }
}

async function removeFav(tid) {
  try {
    await fetch('/api/favorites/' + tid, { method: 'DELETE' });
    const el = document.getElementById('fav-' + tid);
    if (el) {
      el.style.opacity = '0';
      el.style.transform = 'translateX(20px)';
      el.style.transition = 'all 0.3s';
      setTimeout(() => el.remove(), 300);
    }
    showToast('已取消收藏');
  } catch (e) {
    showToast('操作失败');
  }
}

// ========== 版面页 ==========
function initBoardsPage() {
  const fetchBtn = document.getElementById('fetch-boards-btn');
  if (fetchBtn) {
    fetchBtn.addEventListener('click', async () => {
      fetchBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 获取中...';
      fetchBtn.disabled = true;
      try {
        const res = await fetch('/api/boards/fetch', { method: 'POST' });
        const data = await res.json();
        showToast('已获取 ' + data.count + ' 个版面');
        location.reload();
      } catch (e) {
        showToast('获取失败: ' + e.message);
        fetchBtn.innerHTML = '<i class="fa-solid fa-download"></i> 从 NGA 获取版面列表';
        fetchBtn.disabled = false;
      }
    });
  }

  // 版面搜索
  const searchInput = document.getElementById('board-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.toLowerCase();
      document.querySelectorAll('.board-card').forEach(el => {
        el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }
}

// ========== 帖子页 ==========
// 帖子页的刷新、收藏、滚动加载等逻辑在各页面内联脚本中处理