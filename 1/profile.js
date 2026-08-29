(()=>{
  const API='http://127.0.0.1:8080';
  const state={userId:null,items:[],traits:[],filtered:[],profile:null,metrics:{},category:'all',query:'',selected:null};
  const el=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const unwrap=json=>json&&Object.prototype.hasOwnProperty.call(json,'data')?json.data:json;
  const categories={
    all:{label:'全部画像',icon:'·'},
    emotion:{label:'情绪与感受',icon:'≈'},
    stress:{label:'压力来源',icon:'↟'},
    sleep:{label:'睡眠与精力',icon:'◒'},
    study:{label:'学习与生活',icon:'◇'},
    coping:{label:'应对方式',icon:'↗'},
    communication:{label:'沟通偏好',icon:'◌'},
    advice:{label:'有效支持',icon:'+'},
    risk:{label:'风险与安全',icon:'!'},
    other:{label:'其他观察',icon:'○'}
  };
  const categoryOf=value=>{
    const key=String(value||'').toLowerCase();
    if(/emotion|mood|feeling/.test(key))return'emotion';
    if(/stress|pressure|trigger/.test(key))return'stress';
    if(/sleep|energy|fatigue/.test(key))return'sleep';
    if(/study|school|work|life/.test(key))return'study';
    if(/coping|habit|strategy/.test(key))return'coping';
    if(/communication|response|preference/.test(key))return'communication';
    if(/advice|support|effective|intervention/.test(key))return'advice';
    if(/risk|crisis|safety/.test(key))return'risk';
    return'other';
  };
  const time=value=>{if(!value)return'暂无时间';const d=new Date(value);return Number.isNaN(d.getTime())?String(value):d.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})};
  const confidence=value=>{const n=Number(value);return Number.isFinite(n)?Math.max(0,Math.min(1,n)):0};
  const confidenceText=value=>{const n=confidence(value);const label=n>=.75?'较高可信':n>=.5?'中等可信':'仍需确认';return`${Math.round(n*100)}% · ${label}`};
  const friendlySource=value=>{
    const source=String(value||'').toLowerCase();
    if(source.includes('recent_history'))return'近期对话';
    if(source.includes('current_message'))return'当前对话';
    if(source.includes('rag'))return'心理知识库';
    if(source.includes('dialogue'))return'对话回应反馈';
    if(source.includes('emotion'))return'情绪分析';
    if(source.includes('profile'))return'画像智能体';
    if(source.includes('assessment'))return'心理测评';
    return value||'智能体观察';
  };
  const cleanEvidence=value=>{
    let text=String(value||'').trim();
    const cutTokens=['document-','-chunk-','crisis_guidelines','student_psychology'];
    if(cutTokens.some(token=>text.toLowerCase().includes(token)))return'该画像由心理知识库支持，具体内部检索标识不在前端展示。';
    return text||'当前画像没有附带可展示的原始依据。';
  };
  const getHeaders=()=>({Accept:'application/json','Content-Type':'application/json'});
  async function request(url,options={}){
    const response=await fetch(url,{...options,headers:{...getHeaders(),...(options.headers||{})}});
    const json=await response.json().catch(()=>({}));
    if(!response.ok||json?.code&&json.code!==200){const error=new Error(json.message||`HTTP ${response.status}`);error.status=response.status;throw error}
    return unwrap(json);
  }
  const normalizeItem=item=>({
    ...item,
    user_id:item.user_id??item.userId,
    create_time:item.create_time??item.createTime,
    update_time:item.update_time??item.updateTime
  });
  const deriveMetrics=items=>{
    const values=items.map(item=>confidence(item.confidence));
    return{
      item_count:items.length,
      category_count:new Set(items.map(item=>categoryOf(item.category))).size,
      average_confidence:values.length?values.reduce((sum,value)=>sum+value,0)/values.length*100:0,
      sensitive_count:items.filter(item=>String(item.sensitivity).toLowerCase()==='sensitive').length,
      last_updated:items[0]?.update_time||items[0]?.create_time||null
    };
  };
  const uniqueBy=(rows,keyOf)=>{
    const seen=new Set();return rows.filter(row=>{const key=keyOf(row);if(!key||seen.has(key))return false;seen.add(key);return true});
  };
  const traitCopy={
    emotion:{title:'情绪反应模式',lead:'近期的情绪体验主要表现为',suffix:'。这些反应会随着环境与压力变化。'},
    stress:{title:'压力反应与来源',lead:'对话中较常出现',suffix:'相关线索，说明这些方面可能正在消耗较多心理精力。'},
    sleep:{title:'睡眠与精力状态',lead:'目前观察到',suffix:'，睡眠可能正在影响日间精力与情绪恢复。'},
    study:{title:'学习与生活重心',lead:'近期生活重心更多集中在',suffix:'，相关任务可能是当前状态的重要背景。'},
    coping:{title:'自我调节方式',lead:'你已经表现出一些可用的调节方式，包括',suffix:'。这些是值得保留的保护性因素。'},
    communication:{title:'沟通与回应偏好',lead:'在交流中更适合',suffix:'，后续回应会尽量遵循这一节奏。'},
    advice:{title:'较适合的支持方式',lead:'当前更可能适合你的支持方向是',suffix:'。建议会结合后续反馈持续修正。'},
    risk:{title:'安全与风险特征',lead:'当前记录中的安全相关观察为',suffix:'。这只用于安全陪伴，不代表医学判断。'},
    other:{title:'其他心理特征',lead:'当前还观察到',suffix:'，仍需要更多对话确认。'}
  };
  function deriveTraits(items){
    const grouped={};items.forEach(item=>{const key=categoryOf(item.category);(grouped[key]||(grouped[key]=[])).push(item)});
    return Object.entries(grouped).map(([key,rows])=>{
      const uniqueValues=uniqueBy([...rows].sort((a,b)=>confidence(b.confidence)-confidence(a.confidence)),item=>String(item.value||'').trim());
      const values=uniqueValues.slice(0,3).map(item=>String(item.value||'').replace(/[。；;]+$/,''));
      const score=uniqueValues.length?uniqueValues.reduce((sum,item)=>sum+confidence(item.confidence),0)/uniqueValues.length:0;
      const evidences=uniqueBy(rows,item=>String(item.evidence||'').trim()).filter(item=>item.evidence);
      const sources=[...new Set(rows.map(item=>friendlySource(item.source)).filter(Boolean))];
      const copy=traitCopy[key]||traitCopy.other;
      return{key,title:copy.title,headline:values[0]||copy.title,description:`${copy.lead}${values.join('、')}${copy.suffix}`,confidence:score,item_count:rows.length,unique_count:uniqueValues.length,sensitive_count:rows.filter(item=>String(item.sensitivity).toLowerCase()==='sensitive').length,sources,evidences,items:rows,last_updated:rows.map(item=>item.update_time||item.create_time).filter(Boolean).sort().at(-1)||null};
    }).sort((a,b)=>b.confidence-a.confidence);
  }
  function mergeServerTraits(derived,serverTraits){
    if(!Array.isArray(serverTraits)||!serverTraits.length)return derived;
    return derived.map(trait=>{
      const matches=serverTraits.filter(row=>categoryOf(row.category)===trait.key);
      if(!matches.length)return trait;
      const weight=matches.reduce((sum,row)=>sum+Number(row.unique_value_count||0),0)||matches.length;
      const score=matches.reduce((sum,row)=>sum+Number(row.average_confidence||0)*(Number(row.unique_value_count||1)),0)/weight;
      const latest=matches.map(row=>row.last_updated).filter(Boolean).sort().at(-1)||trait.last_updated;
      return{...trait,confidence:score,item_count:matches.reduce((sum,row)=>sum+Number(row.item_count||0),0),unique_count:matches.reduce((sum,row)=>sum+Number(row.unique_value_count||0),0),sensitive_count:matches.reduce((sum,row)=>sum+Number(row.sensitive_count||0),0),last_updated:latest};
    }).sort((a,b)=>b.confidence-a.confidence);
  }
  async function load(){
    el('refresh-profile').disabled=true;el('profile-list').innerHTML='<div class="loading">正在读取你的心理画像…</div>';
    try{
      let data;
      try{
        data=await request(`${API}/agent/insights/profile-center?userId=${encodeURIComponent(state.userId)}`);
      }catch(error){
        if(error.status!==404)throw error;
        data=await request(`${API}/agent/insights/session-center?userId=${encodeURIComponent(state.userId)}`);
      }
      state.items=(Array.isArray(data?.profile_items)?data.profile_items:[]).map(normalizeItem);state.profile=data?.profile||null;state.metrics=data?.metrics||deriveMetrics(state.items);state.traits=mergeServerTraits(deriveTraits(state.items),data?.profile_traits);
      renderOverview();renderTraits();renderCategories();applyFilters();renderInsights();
    }catch(error){
      el('trait-list').innerHTML=`<div class="empty">暂时无法读取画像数据<br>${esc(error.message)}<br>请检查 Java 后端连接。</div>`;el('profile-list').innerHTML='';
      renderOverview(true);
    }finally{el('refresh-profile').disabled=false}
  }
  function buildSummary(){
    const explicit=String(state.profile?.summary||'').trim();
    if(explicit&&explicit!=='[]'&&explicit!=='{}'&&!explicit.includes('null')){
      try{
        const raw=JSON.parse(explicit),rows=Array.isArray(raw)?raw:(Array.isArray(raw?.patch_items)?raw.patch_items:[]);
        if(rows.length){
          const values=rows.map(row=>String(row.value||'').trim()).filter(Boolean).slice(0,3);
          if(values.length)return`目前主要观察到：${values.join('；')}。这些画像会随着后续对话持续更新。`;
        }
      }catch(error){/* 非 JSON 的正常文字摘要直接展示。 */}
      if(!explicit.startsWith('[')&&!explicit.startsWith('{'))return explicit;
    }
    if(!state.traits.length)return'当前画像仍在形成中。完成更多自然对话后，心晴 AI 会逐步了解你的状态。';
    const important=state.traits.slice(0,3).map(trait=>trait.headline);
    return`目前形成的主要特征包括：${important.join('；')}。这是对多轮对话的综合理解，会随着后续交流持续修正。`;
  }
  function renderOverview(error=false){
    const metrics=state.metrics||{},latest=metrics.last_updated||state.items[0]?.update_time||state.items[0]?.create_time;
    el('summary-title').textContent=error?'画像暂时无法更新':state.items.length?'心晴 AI 正在逐步了解你':'画像正在形成中';
    el('summary-copy').textContent=error?'请检查后端连接后重新刷新页面。':buildSummary();
    el('summary-time').textContent=latest?`更新于 ${time(latest)}`:'暂无更新时间';
    el('metric-items').textContent=error?'—':state.traits.length;
    el('metric-categories').textContent=error?'—':state.items.length;
    el('metric-confidence').textContent=error?'—':`${Math.round(Number(metrics.average_confidence||0))}%`;
    el('metric-sensitive').textContent=error?'—':metrics.sensitive_count??state.items.filter(item=>String(item.sensitivity).toLowerCase()==='sensitive').length;
  }
  function renderTraits(){
    el('evidence-count').textContent=`${state.items.length} 条依据`;
    if(!state.traits.length){el('trait-list').innerHTML='<div class="empty">综合心理特征仍在形成中。<br>完成更多自然对话后，这里会逐步出现稳定特征。</div>';return}
    el('trait-list').innerHTML=state.traits.map(trait=>{
      const meta=traitCopy[trait.key]||traitCopy.other,score=Math.round(trait.confidence*100),stable=score>=70&&trait.unique_count>=1;
      return`<button class="trait-card" type="button" data-trait="${esc(trait.key)}"><div class="trait-top"><span class="trait-name"><i>${esc(categories[trait.key]?.icon||'○')}</i>${esc(meta.title)}</span><span class="trait-state">${stable?'较明确':'正在形成'}</span></div><h3>${esc(trait.headline)}</h3><p>${esc(trait.description)}</p><div class="trait-meta"><span>${trait.unique_count} 个不同观察</span><span>${trait.sources.length} 类来源</span><span>可信度 ${score}%</span></div></button>`;
    }).join('');
  }
  function categoryCounts(){
    const counts={all:state.items.length};Object.keys(categories).forEach(key=>{if(key!=='all')counts[key]=0});
    state.items.forEach(item=>counts[categoryOf(item.category)]++);return counts;
  }
  function renderCategories(){
    const counts=categoryCounts(),present=Object.keys(categories).filter(key=>key==='all'||counts[key]>0);
    el('dimension-count').textContent=`${Math.max(0,present.length-1)} 个维度`;
    el('category-list').innerHTML=present.map(key=>`<button class="category-button ${state.category===key?'active':''}" type="button" data-category="${key}"><span class="category-icon">${categories[key].icon}</span><span>${categories[key].label}</span><span class="category-count">${counts[key]}</span></button>`).join('');
  }
  function applyFilters(){
    const query=state.query.toLowerCase();
    state.filtered=state.items.filter(item=>(state.category==='all'||categoryOf(item.category)===state.category)&&(!query||`${item.value||''} ${item.evidence||''} ${item.category||''}`.toLowerCase().includes(query)));
    renderItems();
  }
  function renderItems(){
    if(!state.filtered.length){el('profile-list').innerHTML='<div class="empty">当前筛选条件下没有画像内容。<br>画像会随着自然对话逐步形成。</div>';return}
    el('profile-list').innerHTML=state.filtered.map(item=>{
      const category=categoryOf(item.category),score=Math.round(confidence(item.confidence)*100),sensitive=String(item.sensitivity).toLowerCase()==='sensitive';
      return`<button class="profile-card" type="button" data-id="${esc(item.id)}"><div class="card-top"><span class="card-category">${esc(categories[category].label)}</span>${sensitive?'<span class="sensitive">敏感信息</span>':''}</div><h3>${esc(item.value||'暂无画像内容')}</h3><p class="evidence-preview">${esc(cleanEvidence(item.evidence))}</p><div class="confidence"><div class="confidence-track"><i class="confidence-fill" style="--confidence:${score}%"></i></div><span>${score}%</span></div></button>`;
    }).join('');
  }
  function renderInsights(){
    const high=state.items.filter(item=>confidence(item.confidence)>=.75).length,medium=state.items.filter(item=>confidence(item.confidence)>=.5&&confidence(item.confidence)<.75).length,low=state.items.length-high-medium,max=Math.max(1,state.items.length);
    el('confidence-distribution').innerHTML=[['较高可信',high],['中等可信',medium],['仍需确认',low]].map(([label,count])=>`<div class="confidence-row"><span>${label}</span><div class="mini-track"><i style="--value:${count/max*100}%"></i></div><strong>${count}</strong></div>`).join('');
    const sources={};state.items.forEach(item=>{const label=friendlySource(item.source);sources[label]=(sources[label]||0)+1});
    el('source-list').innerHTML=Object.entries(sources).length?Object.entries(sources).map(([label,count])=>`<div class="source-row"><span>${esc(label)}</span><strong>${count}</strong></div>`).join(''):'<div class="source-row"><span>暂无来源数据</span></div>';
    const updates=[...state.items].sort((a,b)=>new Date(b.update_time||b.create_time)-new Date(a.update_time||a.create_time)).slice(0,5);
    el('update-list').innerHTML=updates.length?updates.map(item=>`<div class="update-row"><i class="update-dot"></i><div><b>${esc(String(item.value||'画像已更新').slice(0,28))}</b><time>${esc(time(item.update_time||item.create_time))}</time></div></div>`).join(''):'<div class="update-row"><div>暂无画像变化记录</div></div>';
  }
  function openTraitDrawer(trait){
    state.selected=null;el('drawer-title').textContent=trait.title;el('drawer-value').textContent=trait.description;
    el('drawer-confidence').textContent=confidenceText(trait.confidence);el('drawer-source').textContent=trait.sources.join('、')||'暂无来源';el('drawer-sensitivity').textContent=trait.sensitive_count?`${trait.sensitive_count} 条敏感依据`:'普通信息';el('drawer-time').textContent=time(trait.last_updated);
    const evidenceRows=trait.evidences.slice(0,6).map(item=>`<div class="drawer-trait-item"><strong>${esc(item.value||'形成依据')}</strong>${esc(cleanEvidence(item.evidence))}</div>`).join('');
    el('drawer-evidence').innerHTML=evidenceRows?`<div class="drawer-trait-list">${evidenceRows}</div>`:'当前综合特征没有可展示的原始依据。';
    el('edit-section').hidden=true;el('save-profile').hidden=true;el('delete-profile').hidden=true;
    el('profile-drawer').classList.add('open');el('drawer-backdrop').classList.add('open');document.body.style.overflow='hidden';el('drawer-close').focus();
  }
  function openDrawer(item){
    state.selected=item;el('drawer-title').textContent=categories[categoryOf(item.category)].label;el('drawer-value').textContent=item.value||'暂无画像内容';
    el('drawer-confidence').textContent=confidenceText(item.confidence);el('drawer-source').textContent=friendlySource(item.source);el('drawer-sensitivity').textContent=String(item.sensitivity).toLowerCase()==='sensitive'?'敏感信息':'普通信息';el('drawer-time').textContent=time(item.update_time||item.create_time);el('drawer-evidence').textContent=cleanEvidence(item.evidence);el('edit-value').value=item.value||'';
    const editable=item.editable===true||item.editable===1;const deletable=item.deletable===true||item.deletable===1;
    el('edit-section').hidden=!editable;el('save-profile').hidden=!editable;el('delete-profile').hidden=!deletable;
    el('profile-drawer').classList.add('open');el('drawer-backdrop').classList.add('open');document.body.style.overflow='hidden';el('drawer-close').focus();
  }
  function closeDrawer(){el('profile-drawer').classList.remove('open');el('drawer-backdrop').classList.remove('open');document.body.style.overflow='';state.selected=null}
  function toast(message){const node=el('profile-toast');node.textContent=message;node.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.classList.remove('show'),2600)}
  async function saveSelected(){
    if(!state.selected)return;const value=el('edit-value').value.trim();if(!value){toast('画像内容不能为空');return}
    el('save-profile').disabled=true;
    try{await request(`${API}/agent/insights/profile-item?userId=${encodeURIComponent(state.userId)}`,{method:'PUT',body:JSON.stringify({id:state.selected.id,value,evidence:state.selected.evidence||''})});toast('画像修正已保存');closeDrawer();await load()}catch(error){toast(error.message)}finally{el('save-profile').disabled=false}
  }
  async function deleteSelected(){
    if(!state.selected||!confirm('确定删除这条画像吗？删除后将不再用于后续个性化回应。'))return;
    el('delete-profile').disabled=true;
    try{await request(`${API}/agent/insights/profile-item?userId=${encodeURIComponent(state.userId)}&id=${encodeURIComponent(state.selected.id)}`,{method:'DELETE'});toast('画像已删除');closeDrawer();await load()}catch(error){toast(error.message)}finally{el('delete-profile').disabled=false}
  }
  el('category-list').addEventListener('click',event=>{const button=event.target.closest('.category-button');if(!button)return;state.category=button.dataset.category;renderCategories();applyFilters()});
  el('trait-list').addEventListener('click',event=>{const card=event.target.closest('.trait-card');if(!card)return;const trait=state.traits.find(row=>row.key===card.dataset.trait);if(trait)openTraitDrawer(trait)});
  el('profile-list').addEventListener('click',event=>{const card=event.target.closest('.profile-card');if(!card)return;const item=state.items.find(row=>String(row.id)===card.dataset.id);if(item)openDrawer(item)});
  el('profile-search').addEventListener('input',event=>{state.query=event.target.value.trim();applyFilters()});
  el('refresh-profile').addEventListener('click',load);el('drawer-close').addEventListener('click',closeDrawer);el('drawer-backdrop').addEventListener('click',closeDrawer);el('save-profile').addEventListener('click',saveSelected);el('delete-profile').addEventListener('click',deleteSelected);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&el('profile-drawer').classList.contains('open'))closeDrawer()});
  state.userId=new URLSearchParams(location.search).get('userId')||localStorage.getItem('mood_user_id')||'1';load();
})();
