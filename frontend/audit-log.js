(()=>{
  const API='http://127.0.0.1:8080';
  const state={items:[],filtered:[],selected:null,details:new Map()};
  const el=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const unwrap=json=>json&&Object.prototype.hasOwnProperty.call(json,'data')?json.data:json;
  const bool=value=>value===true||value==='true'||value===1;
  const fmtTime=value=>{if(!value)return '时间未知';const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})};
  const fmtMs=value=>value==null?'—':Number(value)>=1000?`${(Number(value)/1000).toFixed(1)} 秒`:`${value} ms`;
  const statusText=value=>({completed:'完成',partial:'部分完成',failed:'失败',unknown:'未知'}[String(value||'unknown').toLowerCase()]||String(value));
  const decisionText=value=>({allow:'通过',pass:'通过',redact:'脱敏后通过',block:'已阻断'}[String(value||'').toLowerCase()]||value||'未记录');
  const agentName=value=>({safety_gate:'安全检查',initial_analysis:'初步分析',risk_assessment:'风险综合评估',profile_update:'心理画像更新',intervention_plan:'干预方案生成',dialogue:'回复生成',evaluator:'回答质量复核',audit:'审计留痕',crisis_agent:'危机识别',emotion_agent:'情绪理解',rag_agent:'知识检索',trend_agent:'趋势分析',risk_agent:'综合风险判断',profile_agent:'心理画像更新',intervention_agent:'干预建议生成',dialogue_agent:'回复生成',chat_agent:'回复生成',evaluator_agent:'回答质量复核',audit_agent:'审计留痕',blocked:'安全阻断',crisis_response:'危机响应'}[String(value||'').toLowerCase()]||value||'未知步骤');
  const routeName=value=>({exploratory_support:'探索式陪伴',knowledge_support:'知识支持',structured_assessment:'综合评估',follow_up_support:'跟进干预',crisis_response:'危机响应'}[String(value||'').toLowerCase()]||value||'未记录');
  const routeFeatureName=value=>({crisis_level:'危机等级',crisis_action:'危机处置',safety_escalated:'安全门升级',emotion_load:'情绪负荷',trend_load:'历史趋势负荷',knowledge_need:'知识支持需求',follow_up_need:'跟进需求',assessment_evidence:'具备连续评估证据',user_turn_count:'用户历史表达轮数'}[String(value||'')]||value);
  const flagName=value=>({data_minimization:'只保存必要信息',no_raw_chat_in_audit:'审计中不保存聊天原文',java_owns_persistence:'由业务后端统一保存',profile_user_control_enabled:'画像数据由用户掌控',human_review_recommended:'建议人工复核',final_reply_evaluated:'最终回答已复核',final_reply_corrected:'最终回答已修正',rag_has_evidence:'知识引用有依据',rag_no_evidence_declared:'未找到依据时已明确说明',high_risk_safety_first:'高风险场景安全优先',risk_router_hard_constraint:'风险约束路由已强制切换危机响应',safety_allow:'安全检查通过',safety_redact:'敏感信息已脱敏',safety_block:'危险请求已阻断'}[String(value||'').toLowerCase()]||value);
  const json=value=>JSON.stringify(value,null,2);
  async function get(url){const response=await fetch(url,{headers:{Accept:'application/json'}});if(!response.ok)throw new Error(`HTTP ${response.status}`);return unwrap(await response.json())}

  async function load(){
    const userId=new URLSearchParams(location.search).get('userId')||localStorage.getItem('mood_user_id')||'1';
    try{
      const result=await get(`${API}/agent/audit/events?userId=${encodeURIComponent(userId)}&limit=100`);
      state.items=result?.items||[];renderStats();applyFilters();
      if(state.filtered.length)select(state.filtered[0]);else renderEmpty('当前没有可用的审计记录。');
    }catch(error){state.items=[];renderStats();renderEmpty(`暂时无法读取审计记录：${error.message}`);el('record-count').textContent='读取失败'}
  }
  function renderStats(){
    el('stat-total').textContent=state.items.length;
    el('stat-abnormal').textContent=state.items.filter(item=>String(item.status||'unknown').toLowerCase()!=='completed').length;
    el('stat-review').textContent=state.items.filter(item=>bool(item.requires_human_review)).length;
    const traced=state.items.filter(item=>Number(item.trace_event_count||0)>0).length;
    el('stat-traced').textContent=state.items.length?`${traced}/${state.items.length}`:'0';
  }
  function applyFilters(){
    const keyword=el('keyword').value.trim().toLowerCase(),status=el('status-filter').value,review=el('review-filter').value;
    state.filtered=state.items.filter(item=>{
      const hay=[item.request_id,item.session_id,item.model_name,item.workflow_version].join(' ').toLowerCase();
      const current=String(item.status||'unknown').toLowerCase(),reviewValue=bool(item.requires_human_review);
      return (!keyword||hay.includes(keyword))&&(status==='all'||current===status)&&(review==='all'||(review==='yes'&&reviewValue)||(review==='no'&&!reviewValue));
    });renderTable();
  }
  function renderTable(){
    el('record-count').textContent=`${state.filtered.length} 条记录`;
    if(!state.filtered.length){renderEmpty('没有符合筛选条件的审计记录。');return}
    el('table-wrap').innerHTML=`<table class="audit-table"><thead><tr><th style="width:25%">时间与记录</th><th style="width:15%">是否完成</th><th style="width:24%">使用模型</th><th style="width:17%">是否需人工</th><th style="width:19%">响应时间</th></tr></thead><tbody>${state.filtered.map(item=>{
      const status=String(item.status||'unknown').toLowerCase(),review=bool(item.requires_human_review);
      const shortId=item.request_id?`${String(item.request_id).slice(0,8)}…`:'未编号';
      return `<tr class="audit-row ${state.selected?.request_id===item.request_id?'active':''}" data-request="${esc(item.request_id)}"><td><strong>${esc(fmtTime(item.create_time))}</strong><span class="subline" title="${esc(item.request_id)}">记录 ${esc(shortId)}</span></td><td><span class="pill ${esc(status)}">${esc(statusText(status))}</span></td><td><span class="model">${esc(item.model_name||'未记录模型')}</span><span class="subline">版本详情已留存</span></td><td>${review?'<span class="pill review">建议介入</span>':'<span class="subline">无需人工</span>'}</td><td><span class="${Number(item.latency_ms||0)>=10000?'warn':''}">${esc(fmtMs(item.latency_ms))}</span><span class="subline">经过 ${item.trace_event_count??'—'} 个步骤</span></td></tr>`
    }).join('')}</tbody></table>`;
  }
  function renderEmpty(message){el('table-wrap').innerHTML=`<div class="empty">${esc(message)}</div>`}
  async function select(item){
    if(!item)return;state.selected=item;renderTable();el('detail-status').textContent='正在检查';el('detail').innerHTML='<div class="empty loading">正在生成通俗结论…</div>';
    try{let detail=state.details.get(item.request_id);if(!detail){detail=await get(`${API}/agent/audit/events/${encodeURIComponent(item.request_id)}`);state.details.set(item.request_id,detail)}renderDetail(detail,item)}
    catch(error){el('detail-status').textContent='读取失败';el('detail').innerHTML=`<div class="empty">无法读取这条记录：${esc(error.message)}</div>`}
  }
  function renderDetail(detail,item){
    const audit=detail?.audit||{},decisions=audit.decisions||{},min=audit.data_minimization||{},trace=audit.trace_summary||{},routing=audit.routing||detail.routing||{},versions=audit.versions||{},request=detail.request_log||{};
    const timeline=Array.isArray(detail.trace_timeline)?detail.trace_timeline:[],flags=Array.isArray(audit.compliance_flags)?audit.compliance_flags:[];
    const failed=Array.isArray(trace.failed_nodes)?trace.failed_nodes:timeline.filter(step=>step.status==='failed').map(step=>step.agent);
    const status=String(audit.status||item.status||'unknown').toLowerCase(),human=bool(decisions.requires_human_review??item.requires_human_review),corrected=bool(decisions.final_reply_corrected);
    const passed=status==='completed'&&!failed.length;
    const routeReasons=Array.isArray(routing.reasons)?routing.reasons:[];
    const routeFeatures=Object.entries(routing.features||{});
    const routeScores=Object.entries(routing.route_scores||{});
    const plainSummary=passed?(human?'系统已完整执行，但判断本次情况需要专业人员进一步关注。':'系统已按既定流程完成检查，未发现执行异常。'):'系统执行未完全正常，请根据下方失败步骤进一步排查。';
    el('detail-status').textContent=statusText(status);
    el('detail').innerHTML=`
      <section class="detail-hero"><h3>${status==='completed'?'本次检查已完成':status==='failed'?'本次检查执行失败':'本次检查需要关注'}</h3><p>${esc(fmtTime(item.create_time))} · 响应耗时 ${esc(fmtMs(item.latency_ms))}</p><div class="plain-conclusion"><b>一句话结论：</b>${esc(plainSummary)}</div></section>
      <small class="result-help">说明这次回答有没有经过安全检查、是否需要人工兜底。</small>
      <div class="fact-grid">
        <div class="fact"><span>安全检查</span><strong>${esc(decisionText(decisions.safety_decision))}</strong></div>
        <div class="fact"><span>是否人工介入</span><strong class="${human?'bad':'ok'}">${human?'建议专业人员介入':'无需人工介入'}</strong></div>
        <div class="fact"><span>回答质量复核</span><strong>${decisions.evaluator_passed==null?'未记录':decisions.evaluator_passed?'通过':'发现问题'}</strong></div>
        <div class="fact"><span>回答是否修正</span><strong class="${corrected?'warn':'ok'}">${corrected?'复核后已修正':'无需修正'}</strong></div>
        <div class="fact wide"><span>哪个步骤出错</span><strong class="${failed.length?'bad':'ok'}">${esc(failed.length?failed.map(agentName).join('、'):'全部步骤正常')}</strong></div>
      </div>
      <div class="section-label">本次路径依据</div><small class="section-help">系统根据风险、当前需求和已有对话信息选择处理路径；高风险会优先进入危机响应。</small>
      <div class="fact-grid">
        <div class="fact"><span>选择的处理路径</span><strong>${esc(routeName(routing.selected_route||trace.route))}</strong></div>
        <div class="fact"><span>是否需要知识依据</span><strong class="${routing.rag_needed?'warn':'ok'}">${routing.rag_needed?'需要检索支持':'不需要检索支持'}</strong></div>
        <div class="fact"><span>是否满足综合评估条件</span><strong>${routing.evidence_sufficient?'是':'否'}</strong></div>
        <div class="fact"><span>安全强制切换</span><strong class="${routing.hard_constraint_triggered?'bad':'ok'}">${routing.hard_constraint_triggered?'已切换危机响应':'未触发'}</strong></div>
        <div class="fact wide"><span>选择原因</span><strong>${esc(routeReasons.length?routeReasons.join('；'):'旧记录未保存路径依据')}</strong></div>
      </div>
      <details class="detail-card"><summary>路径决策凭证</summary><pre>${esc(json({policy_version:routing.policy_version||'旧版未记录',signals:Object.fromEntries(routeFeatures.map(([key,value])=>[routeFeatureName(key),value])),route_scores:Object.fromEntries(routeScores.map(([key,value])=>[routeName(key),value]))}))}</pre></details>
      <div class="section-label">隐私是否得到保护</div><small class="section-help">审计只留校验凭证，不保存用户说过的完整原话。</small>
      <div class="fact-grid">
        <div class="fact"><span>保存用户原话</span><strong class="${min.raw_message_stored?'bad':'ok'}">${min.raw_message_stored?'是 · 请检查':'否 · 保护隐私'}</strong></div>
        <div class="fact"><span>保存完整聊天历史</span><strong class="${min.full_history_stored?'bad':'ok'}">${min.full_history_stored?'是 · 请检查':'否 · 保护隐私'}</strong></div>
        <div class="fact"><span>参与判断的历史消息</span><strong>${min.history_count??'—'} 条</strong></div>
        <div class="fact"><span>记录保存位置</span><strong>${min.persisted_by_python?'AI 服务':'业务后端统一保存'}</strong></div>
      </div>
      <div class="section-label">系统遵守了哪些规则</div><div class="flag-list">${flags.length?flags.map(flag=>`<span class="flag">✓ ${esc(flagName(flag))}</span>`).join(''):'<span class="subline">未记录合规规则</span>'}</div>
      <div class="section-label">AI 回答经过了哪些步骤</div><small class="section-help">从安全检查到最终留痕，每一步的结果和耗时都可追查。</small><div class="timeline">${timeline.length?timeline.map((step,index)=>`<div class="step ${step.status==='failed'?'failed':''}"><span class="step-dot">${index+1}</span><div class="step-main"><strong>${esc(agentName(step.agent))}</strong><small>${step.status==='failed'?'执行失败':'已完成'}${step.error_code?` · 错误：${esc(step.error_code)}`:''}</small></div><span class="step-time">${esc(fmtMs(step.duration_ms))}</span></div>`).join(''):'<span class="subline">没有步骤记录</span>'}</div>
      <div class="section-label">技术凭证</div><small class="section-help">答辩时无需展开；用于出现争议后精准定位当时使用的规则和程序版本。</small>
      <details class="detail-card"><summary>消息校验码（证明记录未被替换）</summary><pre>原消息：${esc(min.message_hash||request.message_hash||'未记录')}\n脱敏后：${esc(min.redacted_message_hash||request.redacted_message_hash||'未生成')}</pre></details>
      <details class="detail-card"><summary>系统与审计规则版本</summary><pre>${esc(json({workflow_engine:versions.workflow_engine||item.workflow_engine,workflow_version:versions.workflow_version,audit_rule_version:audit.prompt_version||item.workflow_version}))}</pre></details>
      <details class="detail-card"><summary>各智能体版本</summary><pre>${esc(json(versions.agent_versions||{}))}</pre></details>
      <details class="detail-card"><summary>各提示词版本</summary><pre>${esc(json(versions.prompt_versions||{}))}</pre></details>`;
  }
  ['keyword','status-filter','review-filter'].forEach(id=>el(id).addEventListener(id==='keyword'?'input':'change',applyFilters));
  el('table-wrap').addEventListener('click',event=>{const row=event.target.closest('.audit-row');if(row)select(state.filtered.find(item=>String(item.request_id)===row.dataset.request))});
  load();
})();
