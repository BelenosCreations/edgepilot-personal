/* EdgePilot tenant preview. Identity session only; NO legacy/global broker API.
   Never store an EdgePilot password, Public secret, csrf or account data in
   localStorage, sessionStorage, URL parameters or Android app preferences. */
'use strict';
(()=>{
  const el=id=>document.getElementById(id);
  const state={csrf:'',identity:null,connections:[],accounts:[]};
  function status(message,error=false,target='status'){
    const node=el(target);
    if(!node)return;
    node.textContent=message;
    node.classList.toggle('warn',error);
  }
  function showLogin(){
    state.csrf='';
    state.identity=null;
    state.connections=[];
    state.accounts=[];
    el('dashboard').classList.add('hidden');
    el('signIn').classList.remove('hidden');
    el('sessionLabel').textContent='Private account';
    el('password').value='';
    el('apiSecret').value='';
    el('connections').replaceChildren();
    el('brokerAccounts').replaceChildren();
    el('portfolio').replaceChildren();
  }
  async function api(path,method='GET',body){
    const headers={'Accept':'application/json'};
    if(body!==undefined)headers['Content-Type']='application/json';
    if(method!=='GET'&&state.csrf)headers['X-Edge-Identity-CSRF']=state.csrf;
    let response;
    try{
      response=await fetch('/api/identity/'+path,{
        method,headers,body:body===undefined?undefined:JSON.stringify(body),
        cache:'no-store',credentials:'same-origin',redirect:'error'
      });
    }catch(_e){throw Error('EdgePilot could not be reached securely. Retry.');}
    let data={};
    try{data=await response.json();}catch(_e){}
    if(response.status===401){
      showLogin();
      throw Error('Your session has expired. Sign in again.');
    }
    if(!response.ok){
      if(response.status===403)throw Error('Your secure session needs refreshing. Sign in again.');
      if(response.status===429)throw Error('Too many requests. Try again later.');
      throw Error('The requested operation could not be completed securely.');
    }
    return data;
  }
  function node(tag,text,className){
    const result=document.createElement(tag);
    if(text!==undefined)result.textContent=String(text);
    if(className)result.className=className;
    return result;
  }
  function action(label,callback,danger=false){
    const button=node('button',label,danger?'danger':'');
    button.type='button';
    button.addEventListener('click',()=>Promise.resolve().then(()=>callback())
      .catch(e=>status(e.message,true)));
    return button;
  }
  function loginPage(identity){
    state.identity=identity;
    el('welcome').textContent='Signed in as '+String(identity.label||'EdgePilot user')+
      '. Your account and Public connection belong only to you.';
    el('sessionLabel').textContent='Signed in';
    el('signIn').classList.add('hidden');
    el('dashboard').classList.remove('hidden');
  }
  async function loadConnections(){
    const data=await api('public/connections');
    if(!Array.isArray(data.connections))throw Error('Connection status unavailable.');
    state.connections=data.connections;
    const list=el('connections');
    list.replaceChildren();
    if(!data.connections.length){
      list.append(node('p','No Public key saved yet. Save yours above to begin.','muted'));
      return;
    }
    for(const connection of data.connections){
      if(!connection || typeof connection.connectionId!=='string')continue;
      const card=node('div',undefined,'item');
      card.append(node('strong',connection.status==='revoked'?'Disconnected Public key':'Private Public key'));
      card.append(node('small',connection.status==='revoked'?
        'This connection has been revoked.':'Encrypted and saved; verify your Public accounts next.'));
      if(connection.status!=='revoked'){
        const controls=node('div',undefined,'row');
        controls.style.marginTop='12px';
        controls.append(action('Find my accounts',async()=>{
          status('Checking your Public account list (read-only)...');
          const accounts=await api('public/read/connections/'+encodeURIComponent(connection.connectionId)+'/accounts');
          displayDiscovered(connection.connectionId,accounts.accounts);
          status('Your available Public accounts were verified.');
        }));
        const keyField=node('input');
        keyField.type='password';
        keyField.maxLength=2048;
        keyField.autocomplete='off';
        keyField.spellcheck=false;
        keyField.placeholder='Replacement Public key';
        keyField.setAttribute('aria-label','Replacement Public secret');
        card.append(controls,keyField);
        const secondRow=node('div',undefined,'row');
        secondRow.style.marginTop='10px';
        secondRow.append(action('Rotate key',async()=>{
          const secret=keyField.value.trim();keyField.value='';
          if(secret.length<20){status('Enter a valid replacement key.',true);return;}
          if(!confirm('Replacing this key disconnects its previously linked accounts. Continue?'))return;
          await api('public/connections/'+encodeURIComponent(connection.connectionId)+'/rotate',
                    'POST',{secret});
          el('brokerAccounts').replaceChildren();
          el('portfolio').replaceChildren();
          status('Public key replaced. Re-verify your accounts.');
          await loadConnections();await loadAccounts();
        }));
        secondRow.append(action('Disconnect',async()=>{
          if(!confirm('Disconnect this Public key and disable linked accounts?'))return;
          await api('public/connections/'+encodeURIComponent(connection.connectionId),
                    'DELETE');
          el('brokerAccounts').replaceChildren();
          el('portfolio').replaceChildren();
          status('Public key disconnected.');
          await loadConnections();await loadAccounts();
        },true));
        card.append(secondRow);
      }
      list.append(card);
    }
  }
  function displayDiscovered(connectionId,accounts){
    const list=el('brokerAccounts');
    list.replaceChildren();
    if(!Array.isArray(accounts)||accounts.length===0){
      list.append(node('p','No eligible Public accounts were returned.','muted'));return;
    }
    for(const account of accounts){
      if(!account||typeof account.accountId!=='string')continue;
      const card=node('div',undefined,'item');
      card.append(node('strong','Public account '+account.accountId));
      card.append(node('small','Type: '+String(account.accountType||'Unknown')));
      const label=node('input');
      label.maxLength=64;
      label.value='My Public account';
      label.setAttribute('aria-label','Account display label');
      label.style.marginTop='12px';
      card.append(label,action('Link this account',async()=>{
        const value=label.value.trim();
        if(!value||value.length>64){status('Choose an account label.',true);return;}
        await api('public/read/connections/'+encodeURIComponent(connectionId)+'/accounts',
                  'POST',{accountId:account.accountId,label:value});
        status('Your account was linked for read-only access.');
        await loadAccounts();
      }));
      list.append(card);
    }
  }
  async function loadAccounts(){
    const data=await api('accounts');
    if(!Array.isArray(data.accounts))throw Error('Account list unavailable.');
    state.accounts=data.accounts;
    const list=el('portfolio');
    list.replaceChildren();
    if(!data.accounts.length){
      list.append(node('p','After linking an account, its private portfolio appears here.','muted'));
      return;
    }
    for(const account of data.accounts){
      if(!account||typeof account.account_id!=='string')continue;
      const card=node('div',undefined,'item');
      card.append(node('strong',account.label||'My Public account'));
      card.append(node('small','Public • read-only'));
      const info=node('div','Account balance not loaded.','muted');
      info.style.margin='10px 0';
      card.append(info,action('View my portfolio',async()=>{
        status('Loading your private portfolio (read-only)...');
        const result=await api('public/read/accounts/'+encodeURIComponent(account.account_id)+'/portfolio');
        const details=node('div');
        details.append(node('strong','Account value: $'+String(result.balance||'—')));
        if(Array.isArray(result.holdings)){
          for(const holding of result.holdings.slice(0,100)){
            details.append(node('p',String(holding.symbol||'Unknown')+
              ' · Value: $'+String(holding.currentValue||'0')+
              ' · Quantity: '+String(holding.quantity||'0')));
          }
        }
        info.replaceChildren(details);
        status('Your portfolio loaded. Trading and transfers remain disabled.');
      }));
      list.append(card);
    }
  }
  async function refreshAll(){
    await loadConnections();
    await loadAccounts();
    status('Your account is isolated from other EdgePilot users.');
  }
  async function restore(){
    try{
      const data=await api('session');
      state.csrf=data.csrf;
      loginPage(data.user||{});
      await refreshAll();
    }catch(_e){showLogin();}
  }
  el('loginForm').addEventListener('submit',async event=>{
    event.preventDefault();
    const username=el('username').value.trim();
    const password=el('password').value;
    el('password').value='';
    try{
      // No caller-selected owner IDs. Server identifies the principal.
      const response=await api('login','POST',{username,password});
      state.csrf=response.csrf||'';
      const session=await api('session');
      state.csrf=session.csrf||'';
      loginPage(session.user||{});
      await refreshAll();
    }catch(e){
      showLogin();
      status(e.message,true,'loginMessage');
    }
  });
  el('keyForm').addEventListener('submit',async event=>{
    event.preventDefault();
    const secret=el('apiSecret').value.trim();
    el('apiSecret').value='';
    if(secret.length<20){status('Enter your Public API secret to connect.',true);return;}
    try{
      await api('public/connections','POST',{secret});
      status('Your Public key is encrypted. Select Find my accounts to verify it.');
      await loadConnections();
    }catch(e){status(e.message,true);}
  });
  el('refreshButton').addEventListener('click',()=>refreshAll().catch(e=>status(e.message,true)));
  el('logoutButton').addEventListener('click',async()=>{
    try{await api('logout','POST',{});}catch(_e){}
    showLogin();
    status('Signed out of your private account.',false,'loginMessage');
  });
  void restore();
})();
