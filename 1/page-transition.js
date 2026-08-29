(()=>{
  const root=document.documentElement;
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const specialHomeEntry=sessionStorage.getItem('mood-entry')==='home-to-chat'&&location.pathname.toLowerCase().endsWith('/app.html');
  const genericArrival=sessionStorage.getItem('mood-transition')==='content-only';
  if(specialHomeEntry)sessionStorage.removeItem('mood-entry');
  if(genericArrival)sessionStorage.removeItem('mood-transition');
  const style=document.createElement('style');
  style.textContent=`
    @keyframes mood-page-rise{
      from{opacity:0;transform:translateY(26px)}
      to{opacity:1;transform:translateY(0)}
    }
    @keyframes mood-page-leave{
      from{opacity:1;transform:translateY(0)}
      to{opacity:.18;transform:translateY(12px)}
    }
    html.mood-page-enter .top{
      animation:mood-page-rise 620ms cubic-bezier(.22,.7,.31,1) 70ms both
    }
    html.mood-page-enter .layout,
    html.mood-page-enter .content{
      animation:mood-page-rise 720ms cubic-bezier(.22,.7,.31,1) 150ms both
    }
    html.mood-page-leaving .top,
    html.mood-page-leaving .layout,
    html.mood-page-leaving .content{
      pointer-events:none;
      animation:mood-page-leave 220ms cubic-bezier(.55,.05,.7,.25) both
    }
    .mood-page-cover{
      position:fixed;
      inset:0 0 0 var(--mood-cover-left,0px);
      z-index:1000;
      opacity:0;
      pointer-events:none;
      background:
        radial-gradient(ellipse at 86% 18%,rgba(220,235,218,.9),transparent 38%),
        radial-gradient(ellipse at 10% 84%,rgba(246,232,221,.88),transparent 42%),
        #F6F2EA;
      transition:opacity 220ms cubic-bezier(.55,.05,.7,.25)
    }
    .mood-page-cover.is-visible{opacity:1}
    .mood-page-cover.is-clearing{
      opacity:0;
      transition-duration:420ms;
      transition-timing-function:cubic-bezier(.22,.7,.31,1)
    }
    @media(prefers-reduced-motion:reduce){
      html.mood-page-enter .top,
      html.mood-page-enter .layout,
      html.mood-page-enter .content,
      html.mood-page-leaving .top,
      html.mood-page-leaving .layout,
      html.mood-page-leaving .content{animation:none}
      .mood-page-cover{display:none}
    }
  `;
  document.head.append(style);

  const makeCover=incoming=>{
    const cover=document.createElement('div');
    const sidebar=document.querySelector('.mood-sidebar');
    cover.className='mood-page-cover';
    cover.style.setProperty('--mood-cover-left',(sidebar?.getBoundingClientRect().right||0)+'px');
    if(incoming)cover.classList.add('is-visible');
    document.body.append(cover);
    if(incoming){
      requestAnimationFrame(()=>requestAnimationFrame(()=>cover.classList.add('is-clearing')));
      window.setTimeout(()=>cover.remove(),480);
    }
    return cover;
  };

  const enter=()=>{
    if(reduced||specialHomeEntry)return;
    if(genericArrival)makeCover(true);
    root.classList.add('mood-page-enter');
    window.setTimeout(()=>root.classList.remove('mood-page-enter'),900);
  };

  let leaving=false;
  window.moodNavigate=url=>{
    if(leaving)return;
    leaving=true;
    if(reduced){
      window.location.href=url;
      return;
    }
    sessionStorage.setItem('mood-transition','content-only');
    const cover=makeCover(false);
    root.classList.add('mood-page-leaving');
    requestAnimationFrame(()=>cover.classList.add('is-visible'));
    window.setTimeout(()=>{window.location.href=url},220);
  };

  document.addEventListener('click',event=>{
    if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    const link=event.target.closest('a[href]');
    if(!link||link.target==='_blank'||link.hasAttribute('download'))return;
    const raw=link.getAttribute('href');
    if(!raw||raw.startsWith('#')||raw.startsWith('mailto:')||raw.startsWith('tel:'))return;
    const target=new URL(link.href,window.location.href);
    if(target.origin!==window.location.origin)return;
    if(target.pathname===window.location.pathname&&target.hash)return;
    event.preventDefault();
    window.moodNavigate(target.href);
  });

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',enter,{once:true});
  else enter();
})();
