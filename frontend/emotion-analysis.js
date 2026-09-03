(() => {
  const API = 'http://127.0.0.1:8080';
  const state = { userId: '1', records: [], unavailableCount: 0, selected: 0 };
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  const unwrap = (json) => json && Object.prototype.hasOwnProperty.call(json, 'data') ? json.data : json;
  const parse = (value, fallback = {}) => {
    if (value == null || value === '') return fallback;
    if (typeof value !== 'string') return value;
    try { return JSON.parse(value); } catch { return fallback; }
  };
  const repairText = (value) => {
    const text = String(value ?? '');
    if (!text || !/[ÃÂäåæçèé]/.test(text) || [...text].some((char) => char.charCodeAt(0) > 255)) return text;
    try { return new TextDecoder('utf-8').decode(Uint8Array.from([...text], (char) => char.charCodeAt(0))); } catch { return text; }
  };
  const score = (value) => {
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, Math.min(100, Math.round(number <= 1 ? number * 100 : number))) : null;
  };
  const time = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  };
  const emotionMap = {
    unknown: '暂未识别', '未知': '暂未识别', uncertainty: '不确定', neutral: '平静', calm: '平静',
    anxious: '焦虑', anxiety: '焦虑', stressed: '压力', stress: '压力', sad: '低落',
    depressed: '低落', depression: '低落', lonely: '孤独', loneliness: '孤独',
    fearful: '恐惧', fear: '恐惧', angry: '愤怒', anger: '愤怒',
    tired: '疲惫', overwhelmed: '不堪重负', irritable: '烦躁', annoyed: '烦躁'
  };
  const dimensionMeta = [
    { key: 'anxiety', label: '焦虑', tone: '#6b7f86', hint: '紧张、担忧与不安信号' },
    { key: 'stress', label: '压力', tone: '#a37a3e', hint: '负担、疲惫与紧绷程度' },
    { key: 'depression', label: '低落', tone: '#a96d68', hint: '低落、无助与动力下降信号' },
    { key: 'loneliness', label: '孤独', tone: '#5c7a63', hint: '孤立感与支持需求信号' }
  ];
  const parseStatusMap = { ok: '结构正常', repaired: '已自动修复', fallback: '降级结果', insufficient_data: '数据不足' };

  function normalize(event) {
    const raw = parse(event.emotionResult ?? event.emotion_result, null);
    if (!raw || typeof raw !== 'object') return null;
    const emotion = repairText(raw.emotion || 'unknown');
    const dimensions = ['anxiety', 'stress', 'depression', 'loneliness']
      .map((key) => score(raw[key]))
      .filter((value) => value != null);
    const insufficient = Boolean(raw.insufficient_data ?? raw.insufficientData);
    return {
      requestId: event.requestId ?? event.request_id ?? '',
      createTime: event.createTime ?? event.create_time,
      emotion,
      anxiety: score(raw.anxiety),
      stress: score(raw.stress),
      depression: score(raw.depression),
      loneliness: score(raw.loneliness),
      confidence: score(raw.confidence),
      evidence: Array.isArray(raw.evidence) ? raw.evidence.map(repairText).filter(Boolean) : [],
      insufficient,
      // “unknown + 数据不足”说明本轮没有可验证的情绪线索，不能作为 0 分情绪点参与趋势计算。
      usable: !insufficient && String(emotion).toLowerCase() !== 'unknown' && dimensions.length > 0,
      reason: repairText(raw.reason || ''),
      parseStatus: raw.parse_status ?? raw.parseStatus ?? 'ok',
      warnings: Array.isArray(raw.validation_warnings) ? raw.validation_warnings : []
    };
  }

  async function request(url) {
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    const json = await response.json().catch(() => ({}));
    if (!response.ok || (json?.code && json.code !== 200)) throw new Error(json?.message || `HTTP ${response.status}`);
    return unwrap(json);
  }

  function label(record) {
    const key = String(record?.emotion || 'unknown').toLowerCase();
    return emotionMap[key] || repairText(record?.emotion) || '暂未识别';
  }

  function strongest(record) {
    return dimensionMeta.reduce((best, item) => {
      const value = Number(record?.[item.key] ?? 0);
      return value > best.value ? { label: item.label, value } : best;
    }, { label: '暂无明显维度', value: 0 });
  }

  function renderPicker() {
    const current = state.records[state.selected];
    $('record-label').textContent = current ? `${time(current.createTime)} · ${label(current)}` : '暂无记录';
    $('record-menu').innerHTML = state.records.length ? `${state.unavailableCount ? `<div class="record-note">另有 ${state.unavailableCount} 条记录未形成可用情绪结论，已不纳入趋势与结果列表。</div>` : ''}${state.records.map((record, index) => {
      const top = strongest(record);
      return `<button class="record-option" type="button" role="option" data-index="${index}" aria-selected="${index === state.selected}">
        <b>${esc(label(record))}</b><time>${esc(time(record.createTime))}</time><span>${record.insufficient ? '数据不足' : `可信度 ${record.confidence ?? 0}%`}</span><em>${esc(top.label)} ${top.value}</em>
      </button>`;
    }).join('')}` : `<div class="empty">${state.unavailableCount ? `最近 ${state.unavailableCount} 条记录均缺少可验证的情绪线索，暂不展示为情绪分析结果。` : '暂无情绪分析记录'}</div>`;
  }

  function renderSnapshot(record) {
    const dataState = record.insufficient ? '当前信息不足，以下分数仅供参考' : '当前情绪分析结果';
    $('snapshot-state').textContent = dataState;
    $('emotion-title').textContent = `主要情绪：${label(record)}`;
    $('emotion-copy').textContent = record.reason || '当前没有返回进一步的情绪说明。';
    $('score-strip').innerHTML = dimensionMeta.map((item) => {
      const value = record[item.key] ?? 0;
      return `<article class="score-tile" aria-label="${item.label}强度 ${value} 分"><span>${item.label}</span><strong>${value} / 100</strong><div class="mini-bar" style="--tone:${item.tone}"><i style="--value:${value}%"></i></div></article>`;
    }).join('');
    $('detail-status').textContent = `${record.insufficient ? '数据不足' : `可信度 ${record.confidence ?? 0}%`} · ${time(record.createTime)}`;
  }

  function pointX(index, total) {
    return total <= 1 ? 50 : 50 + (index * 900 / (total - 1));
  }

  function pointY(value) {
    return 180 - (Math.max(0, Math.min(100, Number(value || 0))) * 1.45);
  }

  function renderTrend() {
    const chronological = [...state.records].reverse().slice(-20);
    if (!chronological.length) {
      $('trend-chart').innerHTML = '<div class="chart-empty">暂无可绘制的情绪记录</div>';
      $('trend-summary').textContent = '历史数据不足';
      return;
    }
    const selectedRecord = state.records[state.selected];
    const selectedIndex = chronological.indexOf(selectedRecord);
    const grid = [0, 25, 50, 75, 100].map((value) => {
      const y = pointY(value);
      return `<line class="grid-line" x1="50" y1="${y}" x2="950" y2="${y}"/><text class="axis-label" x="15" y="${y + 3}">${value}</text>`;
    }).join('');
    const series = dimensionMeta.map((item) => {
      const points = chronological.map((record, index) => `${pointX(index, chronological.length)},${pointY(record[item.key])}`).join(' ');
      const dots = chronological.map((record, index) => `<circle class="series-dot${index === selectedIndex ? ' selected' : ''}" style="--tone:${item.tone}" cx="${pointX(index, chronological.length)}" cy="${pointY(record[item.key])}" r="${index === selectedIndex ? 4.8 : 3}"><title>${time(record.createTime)} · ${item.label} ${record[item.key] ?? 0}</title></circle>`).join('');
      return `<polyline class="series-line" style="--tone:${item.tone}" points="${points}"/>${dots}`;
    }).join('');
    const labels = chronological.map((record, index) => {
      if (chronological.length > 8 && index % Math.ceil(chronological.length / 6) !== 0 && index !== chronological.length - 1) return '';
      return `<text class="axis-label" text-anchor="middle" x="${pointX(index, chronological.length)}" y="204">${time(record.createTime).slice(0, 5)}</text>`;
    }).join('');
    $('trend-chart').innerHTML = `<svg class="trend-chart" viewBox="0 0 980 215" role="img" aria-label="焦虑、压力、低落和孤独变化趋势">${grid}${series}${labels}</svg>`;
    const latest = chronological[chronological.length - 1];
    const previous = chronological[chronological.length - 2];
    if (!previous) $('trend-summary').textContent = '当前仅有一条有效记录';
    else {
      const latestTop = strongest(latest);
      const delta = latestTop.value - Number(previous[dimensionMeta.find((item) => item.label === latestTop.label)?.key] || 0);
      $('trend-summary').textContent = `${latestTop.label}当前最高${delta === 0 ? '，保持稳定' : delta > 0 ? `，较上次上升 ${delta}` : `，较上次下降 ${Math.abs(delta)}`}`;
    }
  }

  function renderComposition(record) {
    $('tab-composition').innerHTML = `<div class="composition">${dimensionMeta.map((item) => {
      const value = record[item.key] ?? 0;
      return `<article class="dimension-card"><header><span>${item.label}</span><strong>${value}</strong></header><p>${item.hint}</p><div class="mini-bar" style="--tone:${item.tone}"><i style="--value:${value}%"></i></div></article>`;
    }).join('')}</div>`;
  }

  function renderEvidence(record) {
    $('tab-evidence').innerHTML = record.evidence.length
      ? `<div class="evidence-list">${record.evidence.map((item) => `<div class="evidence-item">${esc(item)}</div>`).join('')}</div>`
      : '<div class="empty">本轮没有通过原文校验的情绪证据，因此分析可信度会被限制。</div>';
  }

  function renderAnalysis(record) {
    $('tab-analysis').innerHTML = `<div class="analysis-grid">
      <article class="analysis-card"><h3>本轮分析说明</h3><p>${esc(record.reason || '当前没有返回分析说明。')}</p><div class="related-actions"><a class="primary" href="intervention.html">查看个性化建议</a><a href="risk-recognition.html">查看风险识别</a></div></article>
      <article class="analysis-card"><h3>数据状态</h3><div class="status-list">
        <div class="status-row"><span>分析可信度</span><b>${record.confidence ?? 0}%</b></div>
        <div class="status-row"><span>数据充足性</span><b>${record.insufficient ? '数据不足' : '可用于参考'}</b></div>
        <div class="status-row"><span>解析状态</span><b>${esc(parseStatusMap[record.parseStatus] || record.parseStatus)}</b></div>
        <div class="status-row"><span>有效原文依据</span><b>${record.evidence.length} 条</b></div>
      </div></article>
    </div>`;
  }

  function select(index) {
    if (!state.records[index]) return;
    state.selected = index;
    const record = state.records[index];
    renderPicker();
    renderSnapshot(record);
    renderTrend();
    renderComposition(record);
    renderEvidence(record);
    renderAnalysis(record);
  }

  function renderEmpty(message) {
    $('snapshot-state').textContent = '暂无情绪数据';
    $('emotion-title').textContent = '完成一次对话后形成分析';
    $('emotion-copy').textContent = message;
    $('score-strip').innerHTML = dimensionMeta.map((item) => `<article class="score-tile"><span>${item.label}</span><strong>—</strong><div class="mini-bar" style="--tone:${item.tone}"><i style="--value:0%"></i></div></article>`).join('');
    $('trend-chart').innerHTML = '<div class="chart-empty">暂无可绘制的情绪记录</div>';
    $('detail-status').textContent = '等待数据';
    ['tab-composition', 'tab-evidence', 'tab-analysis'].forEach((id) => { $(id).innerHTML = `<div class="empty">${esc(message)}</div>`; });
    renderPicker();
  }

  async function load() {
    try {
      const data = await request(`${API}/agent/insights/session-center?userId=${encodeURIComponent(state.userId)}&limit=20`);
      const allRecords = (data?.recent_audit_events || []).map(normalize).filter(Boolean)
        .sort((a, b) => new Date(b.createTime || 0) - new Date(a.createTime || 0));
      state.unavailableCount = allRecords.filter((record) => !record.usable).length;
      state.records = allRecords.filter((record) => record.usable);
      if (state.records.length) select(0);
      else renderEmpty('最近的智能体链中没有可用情绪分析结果。');
    } catch (error) {
      state.records = [];
      renderEmpty(`暂时无法读取情绪分析：${error.message}`);
    }
  }

  $('record-trigger').addEventListener('click', () => {
    const open = $('record-picker').classList.toggle('open');
    $('record-trigger').setAttribute('aria-expanded', String(open));
  });
  $('record-menu').addEventListener('click', (event) => {
    const option = event.target.closest('.record-option');
    if (!option) return;
    select(Number(option.dataset.index));
    $('record-picker').classList.remove('open');
    $('record-trigger').setAttribute('aria-expanded', 'false');
  });
  document.addEventListener('click', (event) => {
    if (!$('record-picker').contains(event.target)) {
      $('record-picker').classList.remove('open');
      $('record-trigger').setAttribute('aria-expanded', 'false');
    }
  });
  state.userId = new URLSearchParams(location.search).get('userId') || localStorage.getItem('mood_user_id') || '1';
  load();
})();
