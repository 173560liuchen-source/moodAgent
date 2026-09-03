(()=>{
  const API='http://127.0.0.1:8080';
  const state={sessions:[],events:[],filtered:[],selected:null,selectedRound:0,details:new Map()};
  const el=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const unwrap=json=>json&&Object.prototype.hasOwnProperty.call(json,'data')?json.data:json;
  const time=value=>{if(!value)return '时间未知';const d=new Date(value);return Number.isNaN(d.getTime())?String(value):d.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})};
  const riskText=value=>({high:'高风险',medium:'需关注',attention:'需关注',low:'低风险',unknown:'未识别'}[String(value||'unknown').toLowerCase()]||String(value||'未识别'));
  const riskClass=value=>{const v=String(value||'unknown').toLowerCase();return v==='high'?'risk-high':(v==='medium'||v==='attention')?'risk-medium':''};
  const buildRounds=messages=>{const rounds=[];for(const msg of messages||[]){const requestId=msg.request_id||null;const previous=rounds[rounds.length-1];if(msg.role==='user'){rounds.push({user:msg,assistant:null,request_id:requestId})}else if(previous&&!previous.assistant&&(!requestId||!previous.request_id||requestId===previous.request_id)){previous.assistant=msg;previous.request_id=previous.request_id||requestId}else{rounds.push({user:null,assistant:msg,request_id:requestId})}}return rounds};
  const legacyEventForRound=round=>{const target=new Date(round.assistant?.create_time||round.user?.create_time||0).getTime();const candidates=state.events.filter(event=>!state.selected?.time||Math.abs(new Date(event.create_time).getTime()-new Date(state.selected.time).getTime())<86400000);if(!target||!candidates.length)return null;return [...candidates].sort((a,b)=>Math.abs(new Date(a.create_time).getTime()-target)-Math.abs(new Date(b.create_time).getTime()-target))[0]||null};
  const routeLabels={exploratory_support:'探索式陪伴',knowledge_support:'知识支持',structured_assessment:'综合评估',follow_up_support:'跟进干预',crisis_response:'危机响应'};
  const keyResultLabels={safety:'安全检查',crisis:'危机识别',emotion:'情绪分析',rag:'知识检索与引用',profile:'心理画像',intervention:'干预方案',evaluator:'回答评估',audit:'审计记录'};
  const ragWasExecuted=detail=>{const outer=detail?.rag||{},inner=outer.audit_result&&typeof outer.audit_result==='object'?outer.audit_result:{};const strategy=outer.retrieval_strategy??inner.retrieval_strategy;const citations=outer.citations??inner.citations;return Boolean(outer.has_evidence??inner.has_evidence)||(Array.isArray(citations)&&citations.length>0)||Boolean(strategy&&!['skipped','not_applicable'].includes(String(strategy)))};
  const expandTimeline=(detail,steps)=>steps.flatMap(step=>{const name=String(step.agent||step.name||'');if(name!=='initial_analysis')return [step];const metrics=step.metadata?.subagent_duration_ms||{};const expanded=[];const add=(agent,duration)=>expanded.push({...step,agent,duration_ms:duration,error_code:null});if(Object.prototype.hasOwnProperty.call(metrics,'crisis_agent'))add('crisis_agent',metrics.crisis_agent);if(Object.prototype.hasOwnProperty.call(metrics,'emotion_agent'))add('emotion_agent',metrics.emotion_agent);if(Number(metrics.trend_agent)>0)add('trend_agent',metrics.trend_agent);if(ragWasExecuted(detail))add('rag_agent',metrics.rag_agent??0);if(expanded.length)return expanded;return ragWasExecuted(detail)?[step,{...step,agent:'rag_agent',duration_ms:0,error_code:null}]:[step]});
  const resolveRoute=(detail,steps)=>{const auditedRoute=detail.audit?.routing?.selected_route;if(auditedRoute)return auditedRoute;if(detail.route)return detail.route;const names=steps.map(step=>String(step.agent||step.name||''));const nodeSequence=detail.audit?.trace_summary?.node_sequence||[];if(names.includes('crisis_response')||nodeSequence.includes('crisis_response'))return 'crisis_response';if(names.includes('follow_up_assessment')||nodeSequence.includes('follow_up_agent'))return 'follow_up_support';if(names.includes('risk_assessment')||names.includes('profile_update')||names.includes('intervention_plan')||nodeSequence.includes('risk_agent')||nodeSequence.includes('profile_agent')||nodeSequence.includes('intervention_agent'))return 'structured_assessment';if(ragWasExecuted(detail))return 'knowledge_support';return 'exploratory_support'};
  const stepLabel=(name,route)=>{const labels={safety_gate:'安全门',crisis_agent:'危机识别',emotion_agent:'情绪分析',trend_agent:'趋势分析',rag_agent:'RAG 知识检索',risk_assessment:'风险评估',follow_up_assessment:'跟进评估',profile_update:route==='follow_up_support'?'画像增量更新':'画像更新',intervention_plan:route==='follow_up_support'?'干预方案决策':'个性化干预方案',dialogue:'对话回复',evaluator:'回复评估',audit:'审计',crisis_response:'危机响应',blocked:'安全拦截'};if(name==='initial_analysis')return '并行初始分析';return labels[name]||name};
  async function get(url){const response=await fetch(url,{headers:{Accept:'application/json'}});if(!response.ok)throw new Error('HTTP '+response.status);return unwrap(await response.json())}
  async function clearChatRecords(){
    const userId=new URLSearchParams(location.search).get('userId')||localStorage.getItem('mood_user_id')||'1';
    if(!window.confirm('确定清空全部聊天记录吗？此操作无法恢复。'))return;
    const button=el('clear-chat-records');button.disabled=true;button.textContent='正在清空…';
    try{
      const response=await fetch(`${API}/chat/clear`,{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify({userId})});
      const result=await response.json().catch(()=>({}));
      if(!response.ok||result?.code!==200)throw new Error(result?.message||`HTTP ${response.status}`);
      state.sessions=[];state.events=[];state.filtered=[];state.details.clear();clearConversation('聊天记录已清空');renderSessions();renderStats({});
      window.alert(result.message||'聊天记录已清空');
    }catch(error){window.alert(`清空失败：${error.message}`)}
    finally{button.disabled=false;button.textContent='清空聊天记录'}
  }
  async function load(userId){
    el('session-list').innerHTML='<div class="empty loading">正在读取聊天记录和智能体链…</div>';
    try{
      const [center,audit]=await Promise.all([get(`${API}/agent/insights/session-center?userId=${encodeURIComponent(userId)}&limit=20`),get(`${API}/agent/audit/events?userId=${encodeURIComponent(userId)}&limit=100`)]);
      state.sessions=[...(center?.sessions||[])].reverse();state.events=audit?.items||[];localStorage.setItem('mood_user_id',userId);applyFilters();renderStats(center?.status);if(state.filtered.length)selectSession(state.filtered[0]);else clearConversation('没有查询到聊天记录');
    }catch(error){state.sessions=[];state.events=[];el('session-list').innerHTML=`<div class="empty">查询失败：${esc(error.message)}<br>请确认 Java 后端已启动且用户 ID 正确。</div>`;clearConversation('暂时无法加载会话');renderStats({})}
  }
  function renderStats(status={}){
    const rounds=state.sessions.reduce((sum,s)=>sum+buildRounds(s.messages).length,0);
    el('stat-sessions').textContent=state.sessions.length;el('stat-rounds').textContent=rounds;el('stat-risk').textContent=riskText(status.highest_risk_level);el('stat-events').textContent=state.events.length;
  }
  function applyFilters(){
    const key=el('keyword').value.trim().toLowerCase(),risk=el('risk-filter').value,range=el('date-filter').value,now=Date.now();
    state.filtered=state.sessions.filter(session=>{const hay=[session.title,session.preview,...(session.messages||[]).map(m=>m.content)].join(' ').toLowerCase();const date=new Date(session.time).getTime();const dateOk=range==='all'||(range==='today'&&new Date(session.time).toDateString()===new Date().toDateString())||(range==='7d'&&now-date<=7*86400000);const current=String(session.risk_label||'unknown').toLowerCase();const riskOk=risk==='all'||current===risk||(risk==='medium'&&current==='attention');return (!key||hay.includes(key))&&dateOk&&riskOk});renderSessions()
  }
  function renderSessions(){
    el('session-count').textContent=`${state.filtered.length} 条记录`;
    if(!state.filtered.length){el('session-list').innerHTML='<div class="empty">没有符合筛选条件的记录</div>';return}
    el('session-list').innerHTML=state.filtered.map((session,index)=>`<button class="session-card ${state.selected===session?'active':''}" data-index="${index}"><div class="session-meta"><time>${esc(time(session.time))}</time><span class="badge ${riskClass(session.risk_label)}">${esc(riskText(session.risk_label))}</span></div><h3>${esc(session.title||'未命名会话')}</h3><p>${esc(session.preview||'暂无摘要')}</p><div class="badges"><span class="badge">${esc(session.emotion_label||'情绪未识别')}</span><span class="badge">${Number(session.message_count||0)} 条消息</span></div></button>`).join('')
  }
  function selectSession(session){
    state.selected=session;state.selectedRound=0;renderSessions();const rounds=buildRounds(session.messages);el('conversation-title').textContent=session.title||'会话详情';el('conversation-meta').textContent=`${time(session.time)} · ${rounds.length} 轮对话`;
    if(!rounds.length){el('round-list').innerHTML='<div class="empty">该会话没有消息</div>';return}
    el('round-list').innerHTML=rounds.map((round,index)=>`<article class="round"><span class="round-no">${index+1}</span><div class="round-top"><time>${esc(time(round.user?.create_time||round.assistant?.create_time))}</time><button class="chain-button ${index===0?'active':''}" data-round="${index}" data-request="${esc(round.request_id||'')}">查看智能体链</button></div>${round.user?`<div class="message user"><span class="role">用户</span><div class="bubble">${esc(round.user.content)}</div></div>`:''}${round.assistant?`<div class="message assistant"><span class="role">心晴 AI</span><div class="bubble">${esc(round.assistant.content)}</div></div>`:''}</article>`).join('');
    showRoundAnalysis(0)
  }
  async function showRoundAnalysis(index){
    state.selectedRound=index;document.querySelectorAll('.chain-button').forEach((b,i)=>b.classList.toggle('active',i===index));const rounds=buildRounds(state.selected?.messages);const round=rounds[index];if(!round)return;const inferred=!round.request_id;const requestId=round.request_id||(legacyEventForRound(round)?.request_id);if(!requestId){renderLegacyAnalysis();return}
    el('analysis-status').textContent='正在读取';el('analysis-body').innerHTML='<div class="analysis-empty loading">正在读取本轮完整链路…</div>';
    try{let detail=state.details.get(requestId);if(!detail){detail=await get(`${API}/agent/audit/events/${encodeURIComponent(requestId)}`);state.details.set(requestId,detail)}renderAnalysis(detail,{request_id:requestId},null,inferred)}
    catch(error){renderAnalysis(null,{request_id:requestId},error.message)}
  }
  function renderLegacyAnalysis(){el('analysis-status').textContent='旧记录';el('analysis-body').innerHTML='<div class="analysis-empty">该记录生成于精确关联功能上线前，未保存请求标识，无法可靠回放智能体链。</div>'}
  function renderAnalysis(detail,event,error,inferred=false){
    if(!detail||detail.matched===false){el('analysis-status').textContent='未匹配';el('analysis-body').innerHTML=`<div class="analysis-empty">本轮暂无可关联的智能体链记录${error?`<br>${esc(error)}`:''}</div>`;return}
    const timeline=detail.trace_timeline||detail.timeline||detail.trace_events||detail.agent_trace||[];const rawSteps=Array.isArray(timeline)?timeline:[];const routeKey=resolveRoute(detail,rawSteps);const steps=expandTimeline(detail,rawSteps);const emotion=detail.emotion?.emotion||event?.emotion_label||'—';const crisis=detail.crisis?.level||event?.crisis_level||'unknown';const latency=detail.latency_ms??event?.latency_ms??'—';const requestId=detail.request_id||event?.request_id||'—';const route=routeLabels[routeKey]||routeKey;
    el('analysis-status').textContent=steps.length?`${steps.length} 个节点`:'分析摘要';
    el('analysis-body').innerHTML=`<div class="summary-grid"><div class="summary"><span>处理路径</span><strong>${esc(route)}</strong></div><div class="summary"><span>情绪</span><strong>${esc(emotion)}</strong></div><div class="summary"><span>风险等级</span><strong>${esc(riskText(crisis))}</strong></div><div class="summary"><span>总耗时</span><strong>${esc(latency)} ms</strong></div><div class="summary"><span>模型</span><strong>${esc(detail.model_name||event?.model_name||'—')}</strong></div></div><div class="section-label">智能体执行时间线</div>${steps.length?`<div class="chain">${steps.map((step,i)=>{const local=step.duration_ms===0&&['risk_assessment','follow_up_assessment','profile_update','intervention_plan','evaluator','audit'].includes(step.agent||step.name);return `<div class="agent-step"><span class="step-dot">${i+1}</span><div class="step-main"><strong>${esc(stepLabel(step.agent||step.name||'Agent',routeKey))}</strong><small>${esc(local?'本地规则计算（已执行）':(step.status||'已完成'))}${step.error_code?` · ${esc(step.error_code)}`:''}</small></div><span class="step-time">${local?'＜1 ms':step.duration_ms!=null?esc(step.duration_ms)+' ms':'—'}</span></div>`}).join('')}</div>`:'<div class="analysis-empty">该请求未保存节点明细，无法生成时间线。</div>'}<div class="section-label">本轮关键结果</div>${['safety','crisis','emotion','rag','profile','intervention','evaluator','audit'].filter(key=>detail[key]!=null).map(key=>`<details class="detail-card"><summary>${esc(keyResultLabels[key]||key)}</summary><pre>${esc(JSON.stringify(detail[key],null,2))}</pre></details>`).join('')}<div class="detail-card"><h4>请求标识</h4><pre>${esc(requestId)}</pre></div>`
  }
  function clearConversation(message){state.selected=null;el('conversation-title').textContent='会话详情';el('conversation-meta').textContent=message;el('round-list').innerHTML=`<div class="empty">${esc(message)}</div>`;el('analysis-body').innerHTML='<div class="analysis-empty">暂无智能体链数据</div>';el('analysis-status').textContent='等待选择'}
  ['keyword','date-filter','risk-filter'].forEach(id=>el(id).addEventListener(id==='keyword'?'input':'change',applyFilters));
  el('session-list').addEventListener('click',e=>{const card=e.target.closest('.session-card');if(!card)return;const index=Number(card.dataset.index);const session=state.filtered[index];if(session)selectSession(session)});
  el('round-list').addEventListener('click',e=>{const button=e.target.closest('.chain-button');if(button)showRoundAnalysis(Number(button.dataset.round))});
  el('clear-chat-records').addEventListener('click',clearChatRecords);
  const initial=new URLSearchParams(location.search).get('userId')||localStorage.getItem('mood_user_id')||'1';load(initial);
})();
