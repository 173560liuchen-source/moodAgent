(() => {
  const API = 'http://127.0.0.1:8080/agent/gateway';
  const names = {
    student_psychology: '学生心理',
    stress_management: '压力管理',
    sleep_management: '睡眠管理',
    crisis_guidelines: '危机识别',
    school_resources: '校园资源'
  };
  const icons = {
    student_psychology: '心',
    stress_management: '缓',
    sleep_management: '眠',
    crisis_guidelines: '安',
    school_resources: '校'
  };
  const state = { citations: [], filter: 'all' };
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  const unwrap = (payload) => payload && typeof payload === 'object' && 'data' in payload ? payload.data : payload;

  async function request(path, options) {
    const response = await fetch(`${API}${path}`, {
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      ...options
    });
    const text = await response.text();
    let payload;
    try { payload = text ? JSON.parse(text) : {}; } catch { throw new Error(`接口返回了无法解析的内容（HTTP ${response.status}）`); }
    if (!response.ok || payload?.success === false) throw new Error(payload?.message || payload?.error || `请求失败（HTTP ${response.status}）`);
    return unwrap(payload);
  }

  function categoryLabel(value) {
    return names[value] || value || '未分类';
  }

  function policyLabel(value) {
    if (value === 'only_return_real_retrieved_citations') return '只展示真实检索命中的引用依据；知识不足时明确返回无证据，不生成虚构来源。';
    return value || '知识不足时明确说明无证据，不生成虚构来源。';
  }

  function setPipeline(mode) {
    const steps = [...document.querySelectorAll('.pipeline-step')];
    steps.forEach((step) => step.classList.remove('done', 'active'));
    if (mode === 'loading') {
      steps[0]?.classList.add('active');
      $('pipeline-state').textContent = '检索中';
    }
    if (mode === 'done') {
      steps.forEach((step) => step.classList.add('done'));
      $('pipeline-state').textContent = '链路完成';
    }
    if (mode === 'error') $('pipeline-state').textContent = '检索失败';
  }

  function renderCategories(status) {
    const counts = status?.category_counts || {};
    const categories = status?.categories?.length ? status.categories : Object.keys(names);
    const allChunks = Object.values(counts).reduce((sum, item) => sum + Number(item?.chunk_count || item?.chunks || 0), 0);
    const rows = [{ key: 'all', label: '全部分类', docs: status?.document_count || 0, chunks: allChunks }, ...categories.map((key) => {
      const item = counts[key] || {};
      return {
        key,
        label: categoryLabel(key),
        docs: Number(item.document_count ?? item.documents ?? 0),
        chunks: Number(item.chunk_count ?? item.chunks ?? 0)
      };
    })];
    $('category-total').textContent = `${categories.length} 个分类`;
    $('category-list').innerHTML = rows.map((row) => `
      <button class="category-button${row.key === state.filter ? ' active' : ''}" type="button" data-category="${escapeHtml(row.key)}">
        <span class="category-icon">${escapeHtml(row.key === 'all' ? '全' : icons[row.key] || '知')}</span>
        <span class="category-name">${escapeHtml(row.label)}<small>${row.docs} 份文档</small></span>
        <span class="category-count">${row.chunks}</span>
      </button>`).join('');
  }

  async function loadStatus() {
    try {
      const status = await request('/rag/status');
      const ready = String(status?.status || '').toLowerCase() === 'ready';
      $('status-main').classList.add(ready ? 'ready' : 'error');
      $('status-value').textContent = ready ? '知识库已就绪' : (status?.status || '状态异常');
      $('status-detail').textContent = ready
        ? `${status.vector_store} 正常连接`
        : (status?.message || '向量存储暂时不可用');
      $('document-count').textContent = Number(status?.document_count || 0).toLocaleString('zh-CN');
      $('chunk-count').textContent = Number(status?.chunk_count || 0).toLocaleString('zh-CN');
      $('collection-name').textContent = status?.collection || '未返回集合名称';
      $('model-name').textContent = String(status?.embedding_model || '—').replace(/^.*\//, '');
      $('evidence-policy').textContent = policyLabel(status?.evidence_policy);
      renderCategories(status);
    } catch (error) {
      $('status-main').classList.add('error');
      $('status-value').textContent = '暂时无法连接';
      $('status-detail').textContent = error.message;
      renderCategories({ categories: Object.keys(names), category_counts: {} });
    }
  }

  function renderCitations() {
    const list = state.filter === 'all' ? state.citations : state.citations.filter((item) => item.category === state.filter);
    $('citation-count').textContent = `${list.length} 条依据`;
    if (!list.length) {
      $('citation-list').innerHTML = `<div class="empty"><div><b>${state.citations.length ? '此分类没有命中依据' : '没有找到可靠依据'}</b>${state.citations.length ? '请选择其他分类查看本次检索结果。' : '可以调整问题描述、返回条数或最低相关度后重试。'}</div></div>`;
      return;
    }
    $('citation-list').innerHTML = list.map((item, index) => {
      const score = Number(item.score);
      const scoreText = Number.isFinite(score) ? `${Math.round(score * 100)}%` : '—';
      const title = item.source || item.file_name || `知识来源 ${index + 1}`;
      const details = [
        item.heading_path ? `章节：${item.heading_path}` : '',
        item.file_type ? `类型：${item.file_type}` : '',
        item.char_start != null && item.char_end != null ? `位置：${item.char_start}–${item.char_end}` : '',
        item.document_id ? `文档 ID：${item.document_id}` : '',
        item.chunk_id ? `片段 ID：${item.chunk_id}` : ''
      ].filter(Boolean).join('\n');
      return `<article class="citation">
        <div class="citation-top"><span class="citation-source">${escapeHtml(title)}</span><span class="badge">${escapeHtml(categoryLabel(item.category))}</span><span class="score">${scoreText}</span></div>
        <p>${escapeHtml(item.content || '该依据未返回可展示的正文。')}</p>
        ${details ? `<details><summary>查看技术信息</summary><div class="tech">${escapeHtml(details)}</div></details>` : ''}
      </article>`;
    }).join('');
  }

  function renderResult(result) {
    state.citations = Array.isArray(result?.citations) ? result.citations : [];
    state.filter = 'all';
    document.querySelectorAll('.category-button').forEach((button) => button.classList.toggle('active', button.dataset.category === 'all'));
    $('result-summary').classList.add('show');
    $('rewritten-query').textContent = result?.rewritten_query || result?.query || '未重写';
    $('selected-categories').textContent = (result?.selected_categories || []).map(categoryLabel).join('、') || '自动选择';
    $('retrieval-strategy').textContent = result?.retrieval_strategy || '—';
    const confidence = Number(result?.confidence);
    $('result-confidence').textContent = Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : '—';
    if (result?.evidence_policy) $('evidence-policy').textContent = policyLabel(result.evidence_policy);
    renderCitations();
  }

  $('min-score').addEventListener('input', (event) => {
    $('score-output').textContent = Number(event.target.value).toFixed(2);
  });

  $('category-list').addEventListener('click', (event) => {
    const button = event.target.closest('.category-button');
    if (!button) return;
    state.filter = button.dataset.category;
    document.querySelectorAll('.category-button').forEach((item) => item.classList.toggle('active', item === button));
    renderCitations();
  });

  $('rag-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const query = $('rag-query').value.trim();
    if (!query) return;
    const button = $('search-button');
    button.disabled = true;
    button.textContent = '正在检索';
    $('error-box').classList.remove('show');
    $('citation-list').innerHTML = '<div class="empty"><div><b>正在检索真实知识片段</b>系统正在理解问题并重排相关依据。</div></div>';
    $('citation-count').textContent = '检索中';
    setPipeline('loading');
    try {
      const result = await request('/rag/search', {
        method: 'POST',
        body: JSON.stringify({
          query,
          history: [],
          top_k: Math.max(1, Math.min(20, Number($('top-k').value) || 5)),
          min_score: Number($('min-score').value)
        })
      });
      renderResult(result);
      setPipeline('done');
    } catch (error) {
      state.citations = [];
      renderCitations();
      $('error-box').textContent = error.message;
      $('error-box').classList.add('show');
      setPipeline('error');
    } finally {
      button.disabled = false;
      button.textContent = '检索知识';
    }
  });

  loadStatus();
})();
