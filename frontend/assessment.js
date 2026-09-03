(() => {
  const API = new URLSearchParams(location.search).get('api') || 'http://localhost:8080';
  const state = { questions: [], options: [], answers: new Map(), submitting: false, history: [] };
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  const unwrap = (json) => json && Object.prototype.hasOwnProperty.call(json, 'data') ? json.data : json;
  const getUserId = () => new URLSearchParams(location.search).get('userId') || localStorage.getItem('mood_user_id') || '1';

  function toast(message) {
    $('toast').textContent = message;
    $('toast').classList.add('show');
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => $('toast').classList.remove('show'), 2800);
  }

  async function request(url, options = {}) {
    const token = localStorage.getItem('token') || localStorage.getItem('mood_token');
    const response = await fetch(url, {
      ...options,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {})
      }
    });
    const json = await response.json().catch(() => ({}));
    if (!response.ok || (json?.code && json.code !== 200)) {
      throw new Error(json?.message || `HTTP ${response.status}`);
    }
    return unwrap(json);
  }

  function renderQuestions(data) {
    state.questions = Array.isArray(data?.questions) ? data.questions : [];
    state.options = Array.isArray(data?.options) ? data.options : [];
    if (state.questions.length !== 20 || state.options.length !== 4) {
      throw new Error('后端未返回完整的20题标准量表');
    }
    $('question-status').textContent = '20题 · 每题必答';
    $('question-list').innerHTML = state.questions.map((question, index) => `
      <fieldset class="question">
        <legend class="sr-only">第${index + 1}题：${esc(question.title)}</legend>
        <div class="question-head">
          <span class="question-no">${index + 1}</span>
          <p class="question-title">${esc(question.title)}</p>
          <span class="dimension">${esc(question.dimension || '状态评估')}</span>
        </div>
        <div class="options">
          ${state.options.map((option) => `
            <span class="option">
              <input id="q${index}-${option.value}" type="radio" name="q${index}" value="${option.value}">
              <label for="q${index}-${option.value}">${esc(option.label)}</label>
            </span>
          `).join('')}
        </div>
      </fieldset>
    `).join('');
    updateProgress();
  }

  function renderLoadError(message) {
    $('question-status').textContent = '加载失败';
    $('question-list').innerHTML = `<div class="error"><div><p>${esc(message)}</p><button id="retry-load" type="button">重新加载</button></div></div>`;
    $('retry-load').addEventListener('click', loadQuestions);
  }

  function updateProgress() {
    const completed = state.answers.size;
    const progress = Math.round(completed / 20 * 100);
    $('progress-number').textContent = `${completed}/20`;
    $('progress-ring').style.setProperty('--progress', `${progress}%`);
    $('submit-assessment').disabled = completed !== 20 || state.submitting;
    $('submit-assessment').textContent = completed === 20 ? '查看量化结果' : `还需完成 ${20 - completed} 题`;
    $('question-status').textContent = `${completed}/20 已作答`;
  }

  function band(score) {
    if (score < 53) return { key: 'normal', label: '正常范围', summary: '当前结果处于正常范围，暂未提示明显的抑郁情绪。' };
    if (score < 63) return { key: 'mild', label: '轻度抑郁情绪', summary: '近期存在轻度抑郁情绪信号，建议继续观察并照顾好自己的节奏。' };
    if (score < 73) return { key: 'moderate', label: '中度抑郁情绪', summary: '近期抑郁情绪较为明显，建议接受进一步的专业评估。' };
    return { key: 'severe', label: '重度抑郁情绪', summary: '近期抑郁情绪信号较强，建议尽快寻求精神心理专业支持。' };
  }

  function renderResult(data) {
    const standard = Number(data.standardScore ?? data.score);
    const raw = Number(data.rawScore);
    const currentBand = band(standard);
    $('result-score').textContent = Number.isFinite(standard) ? standard : '—';
    $('result-level').textContent = data.level || currentBand.label;
    $('result-summary-copy').textContent = currentBand.summary;
    $('raw-score').textContent = `${Number.isFinite(raw) ? raw : '—'} / 80`;
    $('standard-score').textContent = `${Number.isFinite(standard) ? standard : '—'} / 100`;
    $('result-suggestion').textContent = data.suggestion || '请结合近期生活状态持续观察自己的情绪变化。';
    const marker = Math.max(0, Math.min(100, (standard - 25) / 75 * 100));
    $('range-marker').style.setProperty('--marker', `${marker}%`);
    $('range-position').textContent = `当前 ${standard} 分`;
    document.querySelectorAll('.quant-table tr').forEach((row) => row.classList.toggle('active', row.dataset.level === currentBand.key));
    $('result').classList.add('visible');
    $('result').setAttribute('aria-hidden', 'false');
    $('result-backdrop').classList.add('visible');
    $('result').scrollTop = 0;
    $('result-close').focus();
  }

  function closeResult() {
    $('result').classList.remove('visible');
    $('result').setAttribute('aria-hidden', 'true');
    $('result-backdrop').classList.remove('visible');
  }

  function formatTime(value) {
    if (!value) return '时间未知';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ');
    return new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
    }).format(date).replaceAll('/', '-');
  }

  function renderHistory(records) {
    state.history = Array.isArray(records) ? records : [];
    $('history-count').textContent = `${state.history.length} 条记录`;
    if (!state.history.length) {
      $('history-list').innerHTML = '<div class="history-empty"><div><b>还没有历史测评</b><span>完成本页测评后，结果会自动保存在这里。</span></div></div>';
      return;
    }
    $('history-list').innerHTML = state.history.map((record, index) => {
      const raw = Number(record.score);
      const standard = Number.isFinite(raw) ? Math.round(raw * 1.25) : null;
      return `<button class="history-card" type="button" data-index="${index}" aria-label="查看${esc(formatTime(record.createTime))}的测评结果">
        <span class="history-score"><strong>${standard ?? '—'}</strong><small>标准分</small></span>
        <span class="history-copy"><strong>${esc(record.result || band(standard).label)}</strong><time>${esc(formatTime(record.createTime))} · ${esc(record.scaleType || 'SDS')}</time><p>${esc(record.suggestion || '查看本次测评详情')}</p></span>
        <span class="history-arrow" aria-hidden="true">›</span>
      </button>`;
    }).join('');
  }

  async function loadHistory() {
    $('history-list').innerHTML = '<div class="history-loading">正在读取历史测评…</div>';
    try {
      const records = await request(`${API}/api/assessment/list?userId=${encodeURIComponent(getUserId())}&limit=20`);
      renderHistory(records);
    } catch (error) {
      $('history-list').innerHTML = `<div class="history-empty"><div><b>暂时无法读取记录</b><span>${esc(error.message)}</span></div></div>`;
    }
  }

  async function clearHistory() {
    if (!state.history.length) {
      toast('没有可清空的测评记录');
      return;
    }
    if (!window.confirm('确定清空全部历史测评记录吗？此操作无法恢复。')) return;
    const button = $('clear-assessment-records');
    button.disabled = true;
    button.textContent = '正在清空…';
    try {
      await request(`${API}/api/assessment/clear`, {
        method: 'POST',
        body: JSON.stringify({ userId: String(getUserId()) })
      });
      state.history = [];
      renderHistory([]);
      toast('历史测评记录已清空');
    } catch (error) {
      toast(`清空失败：${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = '清空记录';
    }
  }

  function openHistory() {
    closeResult();
    $('history-drawer').classList.add('visible');
    $('history-drawer').setAttribute('aria-hidden', 'false');
    $('history-backdrop').classList.add('visible');
    loadHistory();
    $('history-close').focus();
  }

  function closeHistory() {
    $('history-drawer').classList.remove('visible');
    $('history-drawer').setAttribute('aria-hidden', 'true');
    $('history-backdrop').classList.remove('visible');
  }

  async function loadQuestions() {
    $('question-status').textContent = '正在读取标准题目';
    $('question-list').innerHTML = '<div class="loading">正在加载测评题目…</div>';
    try {
      const data = await request(`${API}/assessment/questions?count=20`);
      renderQuestions(data);
    } catch (error) {
      renderLoadError(`暂时无法读取测评题目：${error.message}`);
    }
  }

  $('question-list').addEventListener('change', (event) => {
    const input = event.target.closest('input[type="radio"]');
    if (!input) return;
    const index = Number(input.name.slice(1));
    state.answers.set(index, Number(input.value));
    updateProgress();
  });

  $('assessment-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (state.answers.size !== 20 || state.submitting) return;
    state.submitting = true;
    updateProgress();
    $('submit-assessment').textContent = '正在计算…';
    const userId = getUserId();
    const answers = Array.from({ length: 20 }, (_, index) => state.answers.get(index));
    try {
      const data = await request(`${API}/assessment/submit`, {
        method: 'POST',
        body: JSON.stringify({ userId, answers })
      });
      state.history = [];
      renderResult(data);
    } catch (error) {
      toast(`提交失败：${error.message}`);
    } finally {
      state.submitting = false;
      updateProgress();
    }
  });

  $('restart').addEventListener('click', () => {
    state.answers.clear();
    document.querySelectorAll('#assessment-form input[type="radio"]').forEach((input) => { input.checked = false; });
    closeResult();
    updateProgress();
    $('question-list').scrollTop = 0;
  });
  $('result-close').addEventListener('click', closeResult);
  $('result-backdrop').addEventListener('click', closeResult);
  $('history-trigger').addEventListener('click', openHistory);
  $('clear-assessment-records').addEventListener('click', clearHistory);
  $('history-close').addEventListener('click', closeHistory);
  $('history-backdrop').addEventListener('click', closeHistory);
  $('history-list').addEventListener('click', (event) => {
    const card = event.target.closest('.history-card');
    if (!card) return;
    const record = state.history[Number(card.dataset.index)];
    if (!record) return;
    const raw = Number(record.score);
    const standard = Number.isFinite(raw) ? Math.round(raw * 1.25) : null;
    closeHistory();
    renderResult({ rawScore: raw, standardScore: standard, level: record.result, suggestion: record.suggestion });
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && $('result').classList.contains('visible')) closeResult();
    else if (event.key === 'Escape' && $('history-drawer').classList.contains('visible')) closeHistory();
  });

  loadQuestions();
})();
