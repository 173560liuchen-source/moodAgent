(() => {
  const API = 'http://127.0.0.1:8080';
  const state = { userId: null, plans: [], followUps: [], actionFeedbacks: [], selected: null };
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  const unwrap = (json) => json && Object.prototype.hasOwnProperty.call(json, 'data') ? json.data : json;
  const parse = (value, fallback) => {
    if (value == null || value === '') return fallback;
    if (typeof value !== 'string') return value;
    try { return JSON.parse(value); } catch { return fallback; }
  };
  const array = (value) => {
    const parsed = parse(value, value);
    return Array.isArray(parsed) ? parsed : parsed == null || parsed === '' ? [] : [parsed];
  };
  const levelMap = {
    low: { label: '低负担支持', title: '从一个容易完成的小动作开始' },
    attention: { label: '需要持续关注', title: '保持观察，并主动连接支持' },
    medium: { label: '需要加强支持', title: '优先联系可信任的人或专业支持' },
    high: { label: '安全优先', title: '请优先保证当前安全' }
  };
  const sourceMap = {
    default: '基础安全策略', crisis_agent: '危机识别智能体', risk_agent: '风险识别智能体',
    trend_agent: '趋势分析智能体', emotion_agent: '情绪分析智能体'
  };
  const typeMap = {
    self_regulation: '自我调节', knowledge_recommendation: '知识支持',
    active_check_in: '持续关注', social_support: '可信任支持',
    school_center: '学校心理支持', crisis_response: '紧急安全建议',
    human_review: '线下支持建议'
  };
  const profileMap = {
    sleep_status: '睡眠状态', study_status: '学习状态', coping_method: '应对方式',
    stress_source: '压力来源', effective_advice: '有效建议', support_resource: '支持资源',
    social_status: '社会支持'
  };
  const time = (value) => {
    if (!value) return '时间未知';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  };
  const compact = (value, max = 50) => {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    return text.length > max ? `${text.slice(0, max)}…` : text;
  };
  const cleanEvidence = (value) => {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    if (!text) return '';
    if (/^(rag:|risk_score=|trend:|emotion_scores:)/i.test(text)) {
      if (text.startsWith('risk_score=')) return text.replace('risk_score=', '风险分数 ').replace(', risk_level=', '，风险等级 ');
      if (text.startsWith('trend:')) return text.replace('trend:', '趋势：').replace('stress=', '压力 ').replace(', consecutive_rise=', '，连续上升次数 ');
      if (text.startsWith('emotion_scores:')) return text.replace('emotion_scores:', '情绪强度：').replace('anxiety=', '焦虑 ').replace(', stress=', '，压力 ').replace(', depression=', '，低落 ');
      return '';
    }
    if (/document-|chunk-|crisis_guidelines|student_psychology/i.test(text)) return '';
    return compact(text, 100);
  };
  const cleanDescription = (value) => {
    let text = String(value || '').replace(/\r/g, '\n');
    text = text.replace(/\/?[a-z_]+-document-[a-z0-9]+-chunk-[a-z0-9-]+/gi, '');
    text = text.replace(
      /^依据本地知识库《[^》]+》[^，。]*，可优先选择一个低负担、可立即执行的建议[:：]?/i,
      '建议做法：'
    );
    text = text.split('\n').map((line) => line.trim()).filter((line) =>
      line && !/^(大学生情绪调节\s*RAG\s*知识库|第\s*\d+\s*页|RAG\s*元数据|主题：|使用说明)$/i.test(line)
    ).join('\n');
    text = text
      .replace(/[ \t]+/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/《([^》]+)》\s*，/g, '《$1》，')
      .replace(/^建议做法：\s*上。/, '建议做法：')
      .trim();
    return text;
  };
  const normalize = (raw = {}, meta = {}) => ({
    ...raw,
    requestId: raw.requestId ?? raw.request_id ?? meta.requestId,
    parentPlanId: raw.parentPlanId ?? raw.parent_plan_id,
    revisionNo: Number(raw.revisionNo ?? raw.revision_no ?? 0),
    decisionSource: raw.decisionSource ?? raw.decision_source ?? 'initial',
    level: String(raw.interventionLevel ?? raw.intervention_level ?? 'low').toLowerCase(),
    riskSource: raw.riskLevelSource ?? raw.risk_level_source ?? 'default',
    strategy: raw.strategy || '当前方案未返回策略说明。',
    actions: array(raw.actions),
    rationale: array(raw.rationale),
    safety: array(raw.safetyConstraints ?? raw.safety_constraints),
    profileUsed: array(raw.profileUsed ?? raw.profile_used),
    ragIds: array(raw.ragCitationsUsed ?? raw.rag_citations_used),
    ragGrounding: array(raw.ragGrounding ?? raw.rag_grounding),
    prohibited: array(raw.prohibitedActions ?? raw.prohibited_actions),
    confidence: Number(raw.confidence),
    createTime: raw.createTime ?? raw.create_time ?? meta.createTime,
    eventId: meta.eventId
  });

  async function request(url) {
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    const json = await response.json().catch(() => ({}));
    if (!response.ok || (json?.code && json.code !== 200)) throw new Error(json?.message || `HTTP ${response.status}`);
    return unwrap(json);
  }

  function plansFrom(data) {
    const byRequest = new Map();
    (data?.recent_audit_events || []).forEach((event) => {
      const raw = parse(event.interventionResult ?? event.intervention_result, null);
      if (!raw || typeof raw !== 'object') return;
      const plan = normalize(raw, { requestId: event.requestId ?? event.request_id, createTime: event.createTime ?? event.create_time, eventId: event.id });
      byRequest.set(plan.requestId || `event-${event.id}`, plan);
    });
    const latestRaw = data?.latest_intervention;
    if (latestRaw) {
      const latest = normalize(latestRaw);
      const key = latest.requestId || 'latest';
      const richer = byRequest.get(key);
      byRequest.set(key, richer ? { ...latest, ...richer, createTime: latest.createTime || richer.createTime } : latest);
    }
    return [...byRequest.values()].sort((a, b) => new Date(b.createTime || 0) - new Date(a.createTime || 0));
  }

  const followUpLabels = {
    completed: '已执行', partial: '部分执行', not_started: '未执行', unknown: '执行情况待确认',
    improved: '已有改善', unchanged: '改善不明显', worsened: '状态加重', insufficient_data: '证据不足',
    keep: '保留方案', adjust: '调整方案', replace: '替换方案', escalate: '升级关注'
  };

  function followUpFor(plan) {
    if (!plan?.requestId) return null;
    return state.followUps.find((item) => String(item.adjustedPlanRequestId ?? item.adjusted_plan_request_id ?? '') === String(plan.requestId)) || null;
  }

  function renderFollowUp(plan) {
    const card = $('follow-up-card');
    const followUp = followUpFor(plan);
    if (!followUp) {
      card.hidden = true;
      card.innerHTML = '';
      return;
    }
    const label = (value) => followUpLabels[String(value || '').toLowerCase()] || String(value || '待确认');
    card.hidden = false;
    card.innerHTML = `<div class="follow-up-head"><h3>本次方案跟进</h3><span class="follow-up-status">${esc(label(followUp.decision))}</span></div>
      <div class="follow-up-grid">
        <div class="follow-up-item"><span>执行情况</span><b>${esc(label(followUp.adherence))}</b></div>
        <div class="follow-up-item"><span>效果判断</span><b>${esc(label(followUp.effectiveness))}</b></div>
        <div class="follow-up-item"><span>情绪变化</span><b>${esc(label(followUp.emotionChange ?? followUp.emotion_change))}</b></div>
      </div>
      <p class="follow-up-reason"><b>调整原因：</b>${esc(followUp.adjustmentReason ?? followUp.adjustment_reason ?? '系统已根据本轮反馈更新建议。')}</p>`;
  }

  function renderHistory() {
    $('history-count').textContent = `${state.plans.length} 条`;
    if (!state.plans.length) {
      $('history-list').innerHTML = '<div class="empty"><div><b>暂无干预方案</b>完成一次对话后，系统会自动形成建议。</div></div>';
      return;
    }
    $('history-list').innerHTML = state.plans.map((plan, index) => {
      const info = levelMap[plan.level] || levelMap.low;
      return `<button class="history-card${state.selected === plan ? ' active' : ''}" type="button" data-index="${index}">
        <div class="history-meta"><time>${esc(time(plan.createTime))}</time><span class="level ${esc(plan.level)}">${esc(info.label)}</span></div>
        <h3>${esc(compact(plan.strategy, 34))}</h3>
        <p>${esc(cleanDescription(plan.actions[0]?.description) || '该方案暂未返回行动说明。')}</p>
        <div class="history-foot"><span>第 ${esc(plan.revisionNo || 0)} 版</span><span>${plan.parentPlanId ? `源自方案 #${esc(plan.parentPlanId)}` : '初始方案'}</span></div>
      </button>`;
    }).join('');
  }

  function renderActions(plan) {
    $('action-count').textContent = String(plan.actions.length);
    if (!plan.actions.length) {
      $('action-list').innerHTML = '<div class="empty"><div><b>暂无可展示的行动建议</b>系统只会展示当前真实生成的方案内容。</div></div>';
      return;
    }
    const actions = [...plan.actions].sort((a, b) => Number(a.priority || 99) - Number(b.priority || 99));
    $('action-list').innerHTML = actions.map((action, index) => {
      const profiles = array(action.related_profile_categories);
      const evidence = array(action.evidence).map(cleanEvidence).filter(Boolean).slice(0, 4);
      const actionId = action.action_id || action.actionId || `action-${action.priority || index + 1}`;
      const saved = state.actionFeedbacks.find((item) => String(item.planId ?? item.plan_id) === String(plan.id) && String(item.actionId ?? item.action_id) === String(actionId));
      const feedback = saved ? `<p class="feedback-status">已记录：${esc(saved.executionStatus ?? saved.execution_status)} / ${esc(saved.outcomeStatus ?? saved.outcome_status)}</p>` : '';
      const disabled = plan.id ? '' : ' disabled title="历史审计方案无法提交动作反馈"';
      return `<article class="action-card">
        <div class="action-top"><span class="priority">${esc(action.priority || index + 1)}</span><div class="action-title"><h3>${esc(action.title || `行动建议 ${index + 1}`)}</h3><span>${esc(typeMap[action.action_type] || action.action_type || '个性化建议')}</span></div></div>
        <div class="advice-section"><span class="advice-label">具体建议</span><p>${esc(cleanDescription(action.description) || '该行动暂未返回详细说明。')}</p></div>
        <div class="reason-block"><span class="advice-label">推荐原因</span><p>${esc(action.rationale || '当前未返回推荐原因。')}</p></div>
        ${profiles.length ? `<div class="profile-tags">${profiles.map((item) => `<span class="tag">${esc(profileMap[item] || item)}</span>`).join('')}</div>` : ''}
        ${evidence.length ? `<details><summary>查看分析依据</summary><ul class="basis-list">${evidence.map((item) => `<li>${esc(item)}</li>`).join('')}</ul></details>` : ''}
        <details class="feedback-details">
          <summary>填写执行反馈</summary>
          <form class="feedback-box" data-plan-id="${esc(plan.id || '')}" data-action-id="${esc(actionId)}">
            <label>执行情况<select name="executionStatus"${disabled}><option value="completed">已完成</option><option value="partial">部分完成</option><option value="not_started">未执行</option></select></label>
            <label>主观效果<select name="outcomeStatus"${disabled}><option value="improved">有改善</option><option value="unchanged">没变化</option><option value="worsened">更难受</option><option value="unknown">暂不确定</option></select></label>
            <label>执行难度<select name="difficulty"${disabled}><option value="">未评价</option><option value="1">1 · 很容易</option><option value="2">2 · 较容易</option><option value="3">3 · 一般</option><option value="4">4 · 较难</option><option value="5">5 · 很难</option></select></label>
            <label class="feedback-note">补充原因（可选）<input name="feedbackNote" maxlength="500" placeholder="例如：晚上太累，没有时间完成"${disabled}></label>
            <button class="feedback-submit" type="submit"${disabled}>提交这条行动的反馈</button>
            ${feedback}
          </form>
        </details>
      </article>`;
    }).join('');
  }

  function renderBasis(plan) {
    const reasons = plan.rationale.map(cleanEvidence).filter(Boolean).slice(0, 7);
    $('rationale-list').innerHTML = (reasons.length ? reasons : ['当前方案由风险等级和安全规则共同确定。']).map((item) => `<li>${esc(item)}</li>`).join('');
    $('profile-used').innerHTML = plan.profileUsed.length ? plan.profileUsed.map((item) => `<span class="tag">${esc(profileMap[item] || item)}</span>`).join('') : '<span class="count">本轮没有使用稳定画像特征</span>';
    const grounding = plan.ragGrounding.slice(0, 3);
    $('rag-count').textContent = String(grounding.length || plan.ragIds.length);
    $('rag-grounding').innerHTML = grounding.length ? grounding.map((item) => `<div class="source-row"><b>${esc(item.source || '心理知识库')}</b><span>${esc(item.category || '知识依据')} · ${Math.round(Number(item.score || 0) * 100)}% 相关</span></div>`).join('') : plan.ragIds.length ? `<div class="source-row"><b>${plan.ragIds.length} 条知识依据</b><span>具体内部检索标识已隐藏，可前往 RAG 心理知识库查看。</span></div>` : '<span class="count">本轮方案未使用知识库依据</span>';
    $('safety-list').innerHTML = (plan.safety.length ? plan.safety : ['不做医疗诊断', '不承诺治疗效果']).map((item) => `<li>${esc(item)}</li>`).join('');
    $('prohibited-list').innerHTML = (plan.prohibited.length ? plan.prohibited : ['不得制造恐慌', '不得把普通压力描述为疾病诊断']).map((item) => `<li>${esc(item)}</li>`).join('');
    $('safety-card').className = `basis-card safety ${plan.level === 'high' ? 'high' : ['attention', 'medium'].includes(plan.level) ? 'warn' : ''}`;
  }

  function selectPlan(plan) {
    state.selected = plan;
    const info = levelMap[plan.level] || levelMap.low;
    $('hero').className = `hero ${plan.level}`;
    $('level-label').textContent = info.label;
    $('strategy-title').textContent = info.title;
    const source = plan.decisionSource === 'initial' ? '初始生成' : `跟进决策：${followUpLabels[plan.decisionSource] || plan.decisionSource}`;
    $('strategy-copy').textContent = `${plan.strategy}（${source}）`;
    $('updated-time').textContent = `更新于 ${time(plan.createTime)}`;
    $('confidence').textContent = Number.isFinite(plan.confidence) ? `${Math.round(plan.confidence * 100)}%` : '—';
    $('risk-source').textContent = sourceMap[plan.riskSource] || plan.riskSource || '—';
    renderHistory();
    renderFollowUp(plan);
    renderActions(plan);
    renderBasis(plan);
  }

  function renderEmpty(message = '完成一次新的对话后，系统会自动生成个性化干预建议。') {
    $('level-label').textContent = '暂未形成方案';
    $('strategy-title').textContent = '需要更多对话信息';
    $('strategy-copy').textContent = message;
    $('updated-time').textContent = '暂无更新时间';
    $('confidence').textContent = '—';
    $('risk-source').textContent = '—';
    $('action-count').textContent = '0';
    $('rag-count').textContent = '0';
    $('action-list').innerHTML = '<div class="empty"><div><b>暂无行动建议</b>建议会在正常对话流程中自动生成。</div></div>';
    $('follow-up-card').hidden = true;
    $('follow-up-card').innerHTML = '';
    ['rationale-list', 'safety-list', 'prohibited-list'].forEach((id) => { $(id).innerHTML = '<li>暂无可展示数据</li>'; });
    $('profile-used').innerHTML = '<span class="count">暂无画像依据</span>';
    $('rag-grounding').innerHTML = '<span class="count">暂无知识依据</span>';
  }

  async function load() {
    $('refresh').disabled = true;
    try {
      const data = await request(`${API}/agent/insights/session-center?userId=${encodeURIComponent(state.userId)}&limit=8`);
      state.plans = plansFrom(data);
      state.followUps = Array.isArray(data?.recent_intervention_follow_ups) ? data.recent_intervention_follow_ups : [];
      state.actionFeedbacks = Array.isArray(data?.recent_intervention_action_feedbacks) ? data.recent_intervention_action_feedbacks : [];
      if (state.plans.length) selectPlan(state.plans[0]);
      else { renderHistory(); renderEmpty(); }
    } catch (error) {
      state.plans = [];
      state.followUps = [];
      state.actionFeedbacks = [];
      renderHistory();
      renderEmpty(`暂时无法读取干预方案：${error.message}`);
    } finally {
      $('refresh').disabled = false;
    }
  }

  $('history-list').addEventListener('click', (event) => {
    const card = event.target.closest('.history-card');
    if (!card) return;
    const plan = state.plans[Number(card.dataset.index)];
    if (plan) selectPlan(plan);
  });
  $('action-list').addEventListener('submit', async (event) => {
    const form = event.target.closest('.feedback-box');
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector('button');
    const status = form.querySelector('.feedback-status');
    button.disabled = true;
    try {
      const values = new FormData(form);
      const payload = Object.fromEntries(values.entries());
      payload.planId = Number(form.dataset.planId);
      payload.actionId = form.dataset.actionId;
      if (!payload.difficulty) delete payload.difficulty;
      const response = await fetch(`${API}/agent/insights/intervention-feedback?userId=${encodeURIComponent(state.userId)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(payload)
      });
      const json = await response.json().catch(() => ({}));
      if (!response.ok || (json?.code && json.code !== 200)) throw new Error(json?.message || `HTTP ${response.status}`);
      state.actionFeedbacks.unshift({ ...payload, createTime: new Date().toISOString() });
      selectPlan(state.selected);
    } catch (error) {
      if (status) status.textContent = `提交失败：${error.message}`;
      else form.insertAdjacentHTML('beforeend', `<p class="feedback-status">提交失败：${esc(error.message)}</p>`);
    } finally {
      button.disabled = false;
    }
  });
  $('refresh').addEventListener('click', load);
  state.userId = new URLSearchParams(location.search).get('userId') || localStorage.getItem('mood_user_id') || '1';
  load();
})();
