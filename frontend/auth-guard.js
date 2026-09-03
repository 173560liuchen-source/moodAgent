(()=>{
  const token=localStorage.getItem('mood_token')||localStorage.getItem('token');
  const returnTo=location.pathname.split('/').pop()+location.search+location.hash;
  if(!token){
    document.documentElement.style.visibility='hidden';
    location.replace(`index.html?login=1&return=${encodeURIComponent(returnTo)}`);
    return;
  }

  localStorage.setItem('mood_token',token);
  localStorage.setItem('token',token);
  const currentUserId=Number(localStorage.getItem('mood_user_id'));
  window.moodCurrentUserId=Number.isSafeInteger(currentUserId)&&currentUserId>0?currentUserId:null;

  const currentUrl=new URL(location.href);
  if(currentUrl.searchParams.has('userId')){
    currentUrl.searchParams.delete('userId');
    history.replaceState(null,'',currentUrl.pathname+currentUrl.search+currentUrl.hash);
  }

  const nativeFetch=window.fetch.bind(window);
  const isJavaApi=value=>{
    try{
      const url=new URL(typeof value==='string'?value:value.url,location.href);
      return (url.hostname==='127.0.0.1'||url.hostname==='localhost')&&url.port==='8080';
    }catch{return false}
  };
  const redirectToLogin=()=>{
    localStorage.removeItem('mood_token');localStorage.removeItem('token');localStorage.removeItem('mood_user_id');
    location.replace(`index.html?login=1&expired=1&return=${encodeURIComponent(returnTo)}`);
  };
  window.fetch=async(input,init={})=>{
    const options={...init};
    if(isJavaApi(input)){
      const headers=new Headers(options.headers||(input instanceof Request?input.headers:undefined));
      if(!headers.has('Authorization'))headers.set('Authorization',`Bearer ${token}`);
      options.headers=headers;
    }
    const response=await nativeFetch(input,options);
    if(response.status===401){redirectToLogin();return response}
    const contentType=response.headers.get('content-type')||'';
    if(contentType.includes('application/json')){
      response.clone().json().then(payload=>{if(payload?.code===401)redirectToLogin()}).catch(()=>{});
    }
    return response;
  };
  window.moodLogout=async()=>{
    try{await window.fetch('http://127.0.0.1:8080/auth/logout',{method:'POST'})}catch{}
    redirectToLogin();
  };
})();
