(()=>{
  const API='http://127.0.0.1:8080';
  const state={events:[],filtered:[],selected:null,userId:null};
  const el=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const unwrap=json=>json&&Object.prototype.hasOwnProperty.call(json,'data')?json.data:json;
  const authHeaders=()=>{const token=localStorage.getItem('token')||localStorage.getItem('mood_token');return token?{Authorization:/^Bearer\s/i.test(token)?token:`Bearer ${token}`}:{}};
  const levels={
    low:{label:'低风险',class:'low',color:'#5c7a63',soft:'#e5eee6',guide:'当前未发现明显危机信号，可以继续关注自己的情绪、压力与睡眠变化。'},
    attention:{label:'需要关注',class:'attention',color:'#a97932',soft:'#f5ead6',guide:'近期状态出现值得关注的变化，建议放慢节奏并持续观察压力和情绪。'},
    high:{label:'高风险',class:'high',color:'#a8554d',soft:'#f4dfdc',guide:'检测到需要立即关注的风险信号，请优先保证当前环境安全并尽快联系可信赖的人。'},
    critical:{label:'紧急风险',class:'critical',color:'#7f3635',soft:'#ecd3d0',guide:'检测到紧急风险信号，请立即保证自身安全，并尽快联系可信赖的人或当地紧急援助服务。'},
    unknown:{label:'尚未识别',class:'unknown',color:'#747d77',soft:'#efefeb',guide:'当前数据不足，完成更多对话后才能形成稳定的风险判断。'}
  };
  const signalDefs=[
    ['self_harm','自伤相关表达'],['harm_to_others','伤害他人表达'],['plan_present','明确计划'],
    ['tool_present','工具或手段'],['time_present','具体时间'],['place_present','具体地点'],['hard_rule_triggered','安全规则触发']
  ];
  const levelInfo=value=>levels[String(value||'unknown').toLowerCase()]||levels.unknown;
  const time=value=>{if(!value)return '时间未知';const d=new Date(value);return Number.isNaN(d.getTime())?String(value):d.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})};
  const compact=(value,max=58)=>{const text=String(value||'').replace(/\s+/g,' ').trim();return text.length>max?text.slice(0,max)+'…':text};
  const number=value=>{if(value==null||value==='')return null;const n=Number(value);return Number.isFinite(n)?Math.max(0,Math.min(100,n)):null};
  const scoreText=value=>{const n=number(value);return n==null?'—':`${Math.round(n)} / 100`};
  const signalCount=signals=>signalDefs.reduce((sum,[key])=>sum+(signals?.[key]===true?1:0),0);
  function initCustomSelect(id,variant='level'){
    const select=el(id),shell=document.createElement('div'),trigger=document.createElement('button'),menu=document.createElement('div');
    select.classList.add('select-native');
    shell.className=`pretty-select ${variant}`;trigger.className='select-trigger';trigger.type='button';trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-label',select.getAttribute('aria-label')||'筛选选项');
    menu.className='select-menu';menu.setAttribute('role','listbox');menu.setAttribute('aria-label',select.getAttribute('aria-label')||'筛选选项');
    select.parentNode.insertBefore(shell,select);shell.append(select,trigger,menu);
    const options=[...select.options];
    const close=()=>{shell.classList.remove('open');trigger.setAttribute('aria-expanded','false')};
    const render=()=>{
      const active=options.find(option=>option.value===select.value)||options[0];
      trigger.innerHTML=`<span class="select-dot ${esc(active.value)}"></span><span class="select-value">${esc(active.textContent)}</span>`;
      [...menu.children].forEach(button=>button.setAttribute('aria-selected',String(button.dataset.value===select.value)));
    };
    options.forEach(option=>{
      const button=document.createElement('button');button.type='button';button.className='select-option';button.dataset.value=option.value;button.setAttribute('role','option');
      button.innerHTML=`<span class="select-dot ${esc(option.value)}"></span><span>${esc(option.textContent)}</span>`;
      button.addEventListener('click',()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));render();close();trigger.focus()});
      button.addEventListener('keydown',event=>{
        if(event.key==='Escape'){event.preventDefault();close();trigger.focus();return}
        if(event.key!=='ArrowDown'&&event.key!=='ArrowUp')return;
        event.preventDefault();const buttons=[...menu.querySelectorAll('.select-option')],index=buttons.indexOf(button),step=event.key==='ArrowDown'?1:-1;
        buttons[(index+step+buttons.length)%buttons.length].focus();
      });
      menu.append(button);
    });
    trigger.addEventListener('click',()=>{
      const opening=!shell.classList.contains('open');
      document.querySelectorAll('.pretty-select.open').forEach(node=>{if(node!==shell){node.classList.remove('open');node.querySelector('.select-trigger')?.setAttribute('aria-expanded','false')}});
      shell.classList.toggle('open',opening);trigger.setAttribute('aria-expanded',String(opening));
      if(opening)requestAnimationFrame(()=>menu.querySelector('[aria-selected=true]')?.focus());
    });
    trigger.addEventListener('keydown',event=>{
      if(event.key!=='ArrowDown'&&event.key!=='ArrowUp')return;
      event.preventDefault();shell.classList.add('open');trigger.setAttribute('aria-expanded','true');
      requestAnimationFrame(()=>menu.querySelector('[aria-selected=true]')?.focus());
    });
    document.addEventListener('click',event=>{if(!shell.contains(event.target))close()});
    render();
  }
  const flatten=value=>{
    const output=[];
    const visit=current=>{
      if(output.length>=5||current==null)return;
      if(typeof current==='string'){const text=cleanAdvice(current);if(text&&!text.startsWith('{'))output.push(text);return}
      if(Array.isArray(current)){current.forEach(visit);return}
      if(typeof current==='object'){
        ['recommendation','suggestions','actions','immediate_actions','coping_steps','content','message'].forEach(key=>visit(current[key]));
      }
    };
    visit(value);
    return [...new Set(output)].slice(0,5);
  };
  async function get(url){const response=await fetch(url,{headers:{Accept:'application/json',...authHeaders()}});if(!response.ok)throw new Error('HTTP '+response.status);const json=await response.json();if(json?.code&&json.code!==200)throw new Error(json.message||'读取失败');return unwrap(json)}
  const helpModal=id=>el(id);
  function closeHelp(){
    document.querySelectorAll('.help-modal.visible').forEach(modal=>{modal.classList.remove('visible');modal.setAttribute('aria-hidden','true')});
    el('help-backdrop').classList.remove('visible');
  }
  function openHelp(id){
    closeHelp();const modal=helpModal(id);modal.classList.add('visible');modal.setAttribute('aria-hidden','false');el('help-backdrop').classList.add('visible');modal.querySelector('[data-close-help]')?.focus();
  }
  function renderHotlines(items){
    const list=Array.isArray(items)?items:[];
    el('hotline-list').innerHTML=list.length?list.map(item=>`<article class="hotline-card"><h3>${esc(item.title||'心理援助热线')}</h3><p>${esc(item.description||'请在服务时间内拨打。')}</p><div class="hotline-actions"><a class="dial-hotline" href="tel:${esc(String(item.phone||'').replace(/[^\d+]/g,''))}">拨打 ${esc(item.phone||'热线')}</a><button class="copy-hotline" type="button" data-phone="${esc(item.phone||'')}">复制号码</button></div></article>`).join(''):'<div class="loading">暂未获取到热线信息，请稍后重试。</div>';
  }
  async function openHotlines(){
    openHelp('hotline-modal');el('hotline-list').innerHTML='<div class="loading">正在读取热线信息…</div>';
    try{renderHotlines(await get(`${API}/help/hotline`))}catch(error){el('hotline-list').innerHTML=`<div class="loading">热线信息暂时无法读取<br>${esc(error.message)}</div>`}
  }
  async function copyHotline(phone){
    if(!phone)return;
    try{await navigator.clipboard.writeText(phone);window.alert('热线号码已复制')}catch(error){window.prompt('请复制热线号码：',phone)}
  }
  async function submitAppointment(event){
    event.preventDefault();const form=event.currentTarget,button=el('appointment-submit'),result=el('appointment-result');
    if(!form.reportValidity())return;
    button.disabled=true;button.textContent='正在提交…';result.textContent='';
    try{
      const response=await fetch(`${API}/help/appoint`,{method:'POST',headers:{'Content-Type':'application/json',Accept:'text/plain',...authHeaders()},body:JSON.stringify({userId:state.userId,name:el('appointment-name').value.trim(),phone:el('appointment-phone').value.trim(),appointTime:el('appointment-time').value})});
      const message=await response.text();let payload;try{payload=JSON.parse(message)}catch(error){}if(!response.ok||(payload?.code&&payload.code!==200))throw new Error(payload?.message||message||`HTTP ${response.status}`);
      result.textContent=payload?.message||message||'预约已提交';form.reset();
    }catch(error){result.textContent=`提交失败：${error.message}`}finally{button.disabled=false;button.textContent='提交预约'}
  }
  async function load(){
    el('refresh-risk').disabled=true;el('event-list').innerHTML='<div class="loading">正在读取风险记录…</div>';
    try{
      const data=await get(`${API}/agent/insights/risk-center?userId=${encodeURIComponent(state.userId)}&limit=30`);
      state.events=Array.isArray(data?.events)?data.events:[];applyFilters();
      if(state.events.length)selectEvent(state.events[0]);else renderEmpty();
    }catch(error){
      el('event-list').innerHTML=`<div class="loading">暂时无法读取风险数据<br>${esc(error.message)}</div>`;
      renderEmpty('请确认 Java 后端已重新启动。');
    }finally{el('refresh-risk').disabled=false}
  }
  function applyFilters(){
    const level=el('level-filter').value,limit=Number(el('range-filter').value);
    state.filtered=state.events.filter(item=>level==='all'||String(item.risk_level||'unknown')===level).slice(0,limit);
    renderEvents();
  }
  function renderEvents(){
    el('event-count').textContent=`${state.filtered.length} 条记录`;
    if(!state.filtered.length){el('event-list').innerHTML='<div class="loading">没有符合条件的风险记录</div>';return}
    el('event-list').innerHTML=state.filtered.map(item=>{const info=levelInfo(item.risk_level),signals=signalCount(item.danger_signals),raw=String(item.conclusion||''),title=/^Python多智能体评估/.test(raw)?`${info.label} · 自动识别结果`:compact(raw||info.guide,32);return `<button class="event-card ${state.selected?.id===item.id?'active':''}" data-id="${esc(item.id)}"><div class="event-meta"><time>${esc(time(item.create_time))}</time><span class="level ${info.class}">${info.label}</span></div><h3>${esc(title)}</h3><p>${esc(compact((item.main_factors||[]).join(' · ')||info.guide))}</p><div class="event-foot"><span>${signals} 个危险信号</span><span>${item.request_id?'链路已记录':'无链路标识'}</span></div></button>`}).join('');
  }
  function selectEvent(item){
    state.selected=item;renderEvents();renderCurrent(item);renderDetail(item);renderGuide(item);renderTrend();
  }
  function renderCurrent(item){
    const info=levelInfo(item.risk_level),signals=signalCount(item.danger_signals);
    const card=el('current-card');card.style.setProperty('--risk-color',info.color);card.style.setProperty('--risk-soft',info.soft);
    el('current-level').textContent=info.label;el('current-conclusion').textContent=cleanConclusion(item.conclusion,info.guide);el('current-time').textContent=`更新于 ${time(item.create_time)}`;
    el('metric-score').textContent=scoreText(item.risk_score);el('metric-emotion').textContent=scoreText(item.emotion_risk);el('metric-trend').textContent=scoreText(item.trend_risk);el('metric-signals').textContent=signals;
  }
  function renderDetail(item){
    const info=levelInfo(item.risk_level);el('detail-status').textContent=time(item.create_time);
    const scores=[['综合风险',item.risk_score],['情绪风险',item.emotion_risk],['趋势风险',item.trend_risk]];
    el('score-row').innerHTML=scores.map(([label,value])=>{const n=number(value);return `<div class="score"><span>${label}</span><strong>${scoreText(value)}</strong><div class="bar"><i style="--value:${n??0}%;--risk-color:${info.color}"></i></div></div>`}).join('');
    const factors=Array.isArray(item.main_factors)?item.main_factors.filter(Boolean):[];
    el('factor-count').textContent=`${factors.length} 项`;el('factor-list').innerHTML=factors.length?factors.map(f=>`<div class="factor">${esc(typeof f==='string'?f:JSON.stringify(f))}</div>`).join(''):'<div class="factor">当前没有可展示的主要影响因素。</div>';
    const signals=item.danger_signals||{};
    el('signal-grid').innerHTML=signalDefs.map(([key,label])=>{const value=signals[key],kind=value===true?'yes':value===false?'no':'unknown',text=value===true?'是':value===false?'否':'未知';return `<div class="signal ${kind}"><span class="signal-name">${label}</span><span class="signal-state">${text}</span></div>`}).join('');
  }
  function renderGuide(item){
    const info=levelInfo(item.risk_level),suggestions=flatten(item.suggestions).concat(flatten(item.intervention)).filter(Boolean);
    document.querySelector('.guide-card.alert').style.setProperty('--risk-color',info.color);
    document.querySelector('.guide-card.alert').style.setProperty('--risk-soft',info.soft);
    el('guide-title').textContent=info.label==='低风险'?'保持当前的自我照顾':'当前安全建议';
    el('guide-copy').textContent=info.guide;
    const defaults=info.class==='low'?['继续留意情绪、压力和睡眠变化','感到不适时可以随时回到会话中心']:['优先保证当前环境安全','及时联系可信赖的人并说明当前感受'];
    const items=[...new Set([...suggestions,...defaults])].slice(0,5);
    el('suggestion-list').innerHTML=items.map(text=>`<li>${esc(compact(text,88))}</li>`).join('');
    el('trace-id').textContent=item.request_id||'暂无请求标识';
    el('chat-link').href=`chat-management.html?userId=${encodeURIComponent(state.userId)}${item.request_id?`&requestId=${encodeURIComponent(item.request_id)}`:''}`;
  }
  function renderTrend(){
    const points=[...state.events].reverse().slice(-12);
    if(points.length<2){el('trend-chart').innerHTML='<div class="trend-empty">至少需要两次风险识别<br>才能展示变化趋势</div>';return}
    const w=290,h=124,pad={l:28,r:9,t:10,b:18};const rank={low:1,attention:2,high:3,critical:4,unknown:0};
    const values=points.map(item=>rank[String(item.risk_level||'unknown')]||0);const max=4;
    const coords=values.map((value,index)=>({x:pad.l+(w-pad.l-pad.r)*(index/Math.max(1,values.length-1)),y:pad.t+(h-pad.t-pad.b)*(1-value/max)}));
    const line=coords.map(p=>`${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');const area=`M ${coords[0].x},${h-pad.b} L ${coords.map(p=>`${p.x},${p.y}`).join(' L ')} L ${coords.at(-1).x},${h-pad.b} Z`;
    el('trend-chart').innerHTML=`<svg class="trend-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="最近风险等级变化趋势"><defs><linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8dae94" stop-opacity=".28"/><stop offset="1" stop-color="#8dae94" stop-opacity="0"/></linearGradient></defs>${[['高',3],['关注',2],['低',1]].map(([label,value])=>{const y=pad.t+(h-pad.t-pad.b)*(1-value/max);return `<line class="trend-grid" x1="${pad.l}" x2="${w-pad.r}" y1="${y}" y2="${y}"/><text class="trend-label" x="1" y="${y+3}">${label}</text>`}).join('')}<path class="trend-area" d="${area}"/><polyline class="trend-line" points="${line}"/>${coords.map(p=>`<circle class="trend-dot" cx="${p.x}" cy="${p.y}" r="3.4"/>`).join('')}</svg>`;
  }
  function cleanConclusion(value,fallback){
    const text=String(value||'').trim();
    if(!text||text.length>=180||/^Python多智能体评估/.test(text))return fallback;
    return text;
  }
  function cleanAdvice(value){
    let text=String(value||'').replace(/\s+/g,' ').trim();
    const tokens=['参考：','参考资料','可参考本地知识库','来源：','crisis_guidelines','student_psychology','document-','-chunk-'];
    let cut=text.length;
    for(const token of tokens){const index=text.toLowerCase().indexOf(token.toLowerCase());if(index>=0)cut=Math.min(cut,index)}
    text=text.slice(0,cut).replace(/[，,、/：:;；\s]+$/,'').trim();
    return text;
  }
  function renderEmpty(extra=''){
    const item={risk_level:'unknown',conclusion:extra||'暂无风险识别数据',danger_signals:{},main_factors:[],suggestions:[]};
    state.selected=item;renderCurrent(item);renderDetail(item);renderGuide(item);renderTrend();
  }
  initCustomSelect('level-filter');initCustomSelect('range-filter','range');
  el('event-list').addEventListener('click',event=>{const card=event.target.closest('.event-card');if(!card)return;const item=state.filtered.find(row=>String(row.id)===card.dataset.id);if(item)selectEvent(item)});
  el('level-filter').addEventListener('change',applyFilters);el('range-filter').addEventListener('change',applyFilters);el('refresh-risk').addEventListener('click',load);
  el('open-hotlines').addEventListener('click',openHotlines);el('open-appointment').addEventListener('click',()=>openHelp('appointment-modal'));el('help-backdrop').addEventListener('click',closeHelp);document.querySelectorAll('[data-close-help]').forEach(button=>button.addEventListener('click',closeHelp));el('hotline-list').addEventListener('click',event=>{const button=event.target.closest('.copy-hotline');if(button)copyHotline(button.dataset.phone)});el('appointment-form').addEventListener('submit',submitAppointment);
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeHelp()});
  const storedUserId=new URLSearchParams(location.search).get('userId')||localStorage.getItem('mood_user_id')||'1';
  const parsedUserId=Number(storedUserId);
  state.userId=Number.isSafeInteger(parsedUserId)&&parsedUserId>0?parsedUserId:1;
  load();
})();
