let base='',csrf='',authenticated=false,snap=null; const $=id=>document.getElementById(id);
const money=x=>Number.isFinite(Number(x))?'$'+Number(x).toFixed(2):'—';
function esc(v){return String(v??'').replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]))}
function tab(id){
 if(id!=='settings'&&$('publicApiSecret'))$('publicApiSecret').value='';
 if(id==='settings'&&authenticated)loadPublicKeyStatus();
 if(id==='markets'&&base&&authenticated)loadScannerConfig();
 if(['auto','micro','fifteen'].includes(id)&&authenticated)loadEngineProfiles();
 if(['auto','micro','fifteen','dash'].includes(id)&&authenticated)loadAutomationStatus();
 if(id==='funds'&&authenticated)loadFundsHistory();
 document.querySelectorAll('.section').forEach(n=>n.classList.toggle('active',n.id===id));
 const top=['dash','auto','micro','fifteen'].includes(id)?id:'more';
 document.querySelectorAll('.nav button').forEach(b=>{const selected=b.dataset.nav===top;b.classList.toggle('active-nav',selected);if(selected)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
}
// Distinct, stored plans -- never enable broker orders or simulated fills.
const ENGINE_INPUTS={
 auto:{stock_allocation:'autoStockAllocation',crypto_allocation:'autoCryptoAllocation',
       max_per_trade:'autoMaxPerTrade',loss_stop:'autoLossStop',profit_target:'autoProfitTarget',
       rolling_loss_stop:'autoRollingLoss',stock_loss_stop:'autoStockLoss',crypto_loss_stop:'autoCryptoLoss',max_open:'autoMaxOpen',stock_market:'autoStocks',crypto_market:'autoCrypto'},
 micro:{allocation:'microAllocation',max_per_trade:'microMaxPerTrade',loss_stop:'microLossStop',
        profit_target:'microProfitTarget',max_trades:'microMaxTradesSession',max_open:'microMaxOpen',
        cooldown_seconds:'microCooldown',stock_market:'microStocks',prediction_market:'microPredictions'},
 fifteen:{allocation:'fifteenAllocation',max_per_trade:'fifteenMaxPerTrade',loss_stop:'fifteenLossStop',
          profit_target:'fifteenProfitTarget',max_trades:'fifteenMaxTradesSession',max_open:'fifteenMaxOpen',
          cooldown_seconds:'fifteenCooldown',minimum_seconds_left:'fifteenMinRemaining',
          max_spread_pct:'fifteenMaxSpread',crypto_market:'fifteenCrypto',
          commodity_market:'fifteenCommodities',fx_market:'fifteenFx'}
};
const ENGINE_INTEGER_FIELDS=new Set(['max_trades','max_open','cooldown_seconds','minimum_seconds_left']);
async function loadEngineProfiles(){
 try {
  const result=await api('engines/config');
  for(const [engine,fields] of Object.entries(ENGINE_INPUTS)){
   const profile=result.profiles?.[engine];if(!profile)continue;
   for(const [key,id] of Object.entries(fields)){
    const input=$(id);if(!input)continue;
    if(input.type==='checkbox')input.checked=profile.config[key]===true;
    else input.value=profile.config[key];
   }
   $(engine+'PlanStatus').textContent=profile.configured
    ? 'Saved '+new Date(profile.updatedAt).toLocaleString()+'. Planning only: no paper or live trading started.'
    : 'Not configured. All engines remain inactive; save these preferences when ready.';
  }
 }catch(e){for(const engine of Object.keys(ENGINE_INPUTS))$(engine+'PlanStatus').textContent='Cannot load saved plan: '+e.message;}
}
async function saveEngineConfig(engine){
 const fields=ENGINE_INPUTS[engine],status=$(engine+'PlanStatus');
 if(!fields)return;
 const payload={};
 for(const [key,id] of Object.entries(fields)){
  const el=$(id);
  payload[key]=el.type==='checkbox'?el.checked:ENGINE_INTEGER_FIELDS.has(key)?Number(el.value):el.value;
 }
 try{
  const out=await api('engines/'+engine+'/config','POST',payload);
  status.textContent='Plan saved. This engine was paused to safely apply changed limits; restart Observe/Paper manually. Live orders remain locked.';await loadAutomationStatus();
 }catch(e){status.textContent='Plan not saved: '+e.message;}
}
function selectFundsGuide(direction){
 $('fundsGuide').textContent=direction==='deposit'
  ? 'Deposit to Public: Open the official Public app → Menu → Deposit, select funding source and destination, review the amount and confirm in Public. No transfer happens here.'
  : 'Withdraw from Public: Open the official Public app → Menu → Withdrawal, choose your connected bank and settled funds, review the details and confirm in Public. Buying power is not necessarily withdrawable.';
}
function openFunds(direction){tab('funds');selectFundsGuide(direction);}
async function loadFundsHistory(){
 const status=$('fundsHistoryStatus'),list=$('fundsHistoryList');
 if(!status||!list)return;
 status.textContent='Reading locally captured Public history…';
 list.replaceChildren();
 try{
  const d=await api('funds/transfer-history');
  if(!d.historyCaptured){
   status.textContent=d.warning||'Synchronize your Public account in Overview first.';
   return;
  }
  status.textContent='Captured sync: '+new Date(d.lastSync).toLocaleString()+'. Transfer-like records may be incomplete. Public History is authoritative.';
  if(!d.entries.length){
   list.textContent='No recognizable transfer-like entries found in captured history. Check Public for complete activity.';
   return;
  }
  for(const x of d.entries){
   const div=document.createElement('div');div.className='log';
   div.textContent=x.label+' · '+(x.timestamp||'Date unavailable')+' · Unverified bank-transfer classification';
   list.append(div);
  }
 }catch(e){status.textContent='Transfer history unavailable: '+e.message;}
}
// v0.2 master automation: browser never places a broker order.
const RISK_TEXT={
 conservative:'0.25% per-trade risk · 1% rolling loss pause · 5% drawdown · 25% exposure',
 balanced:'0.5% per-trade risk · 2% rolling loss pause · 8% drawdown · 50% exposure',
 aggressive:'1% per-trade risk · 3% rolling loss pause · 12% drawdown · 75% exposure'
};
let automationSnapshot=null;
function presentMasterLimits(){
 const el=$('automationProfileLimits');if(el)el.textContent=RISK_TEXT[$('automationRiskLevel').value]||'Unknown risk profile';
}
$('automationRiskLevel').addEventListener('change',presentMasterLimits);
async function loadAutomationStatus(updateFields=false){
 if(!authenticated)return;
 try{
  const data=await api('automation/status');
  automationSnapshot=data;const m=data.master,p=data.paper;
  if(updateFields){
   for(const [field,id] of Object.entries({
    mode:'automationMode',risk_level:'automationRiskLevel',paper_capital:'automationPaperCapital',
    protected_pct:'automationProtectedPct',profit_lock_pct:'automationProfitLock',
    compound_pct:'automationCompoundPct',reserve_profit_pct:'automationReservePct'})){
    $(id).value=m[field];
   }
   presentMasterLimits();
  }
  $('automationMasterBadge').textContent=m.emergency?'EMERGENCY':m.enabled?m.mode.toUpperCase():'OFF';
  $('automationEmergencyReset').disabled=!m.emergency;
  let heartbeat=m.worker_heartbeat?new Date(m.worker_heartbeat).toLocaleString():'No heartbeat yet';
  $('automationMasterStatus').textContent=(data.workerConfigured?'Server worker configured':'Server worker is OFF')+
   ' · '+(m.emergency?'Emergency locked':m.enabled?'Monitor active':'Inactive')+
   ' · Last heartbeat: '+heartbeat+(m.last_error?' · Latest issue: '+m.last_error:'')+
   ' · Live orders disabled. Paper models experimental.';
  $('paperEquity').textContent=money(p.equity);
  $('paperNet').textContent=money(p.realizedNet);
  $('paperExposure').textContent=money(p.exposure);
  $('paperRolling').textContent=money(p.rolling24hRealizedNet);
  for(const [engine,st] of Object.entries(data.engines)){
    $('automationBadge_'+engine).textContent=st.state.toUpperCase();
    $('automationReason_'+engine).textContent=st.reason||'Engine '+st.state+'.';
    $('automationStats_'+engine).textContent='Simulated completed trades: '+st.completedTrades+
      ' · Open paper positions: '+st.openPositions+' · Realized simulated net: '+money(st.netRealized);
  }
  const perf=data.performance||{};
  const lines=['Simulated paper trading only — never broker-confirmed execution.'];
  for(const [engine,stats] of Object.entries(perf.byEngine||{})){
    lines.push(engine.toUpperCase()+': '+stats.trades+' completed · '+
      stats.wins+' wins / '+stats.losses+' losses · '+stats.winRatePct+
      '% modeled win rate · '+money(stats.modeledNet)+' modeled net · '+
      money(stats.assumedFees)+' assumed fees · '+money(stats.closedTradeDrawdown)+
      ' realized closed-trade drawdown');
  }
  if(!(perf.tradesInSample>0))lines.push('No completed simulated trades recorded yet.');
  if(perf.sampleTruncated)lines.push('Partial sample: '+perf.tradesInSample+
      ' of '+perf.totalCompletedTrades+' completed trades.');
  lines.push('Unvalidated strategies: results do not establish predictive advantage.');
  $('automationPerformance').textContent=lines.join('\n');
  const events=$('automationRecentEvents');events.replaceChildren();
  for(const x of (data.events||[]).slice(0,12)){
    const line=document.createElement('div');line.className='log';
    line.textContent=x.ts.slice(0,19)+' · '+(x.engine||'GLOBAL')+' · '+x.event+' · '+x.details;events.append(line);
  }
 }catch(e){$('automationMasterStatus').textContent='Automation controller unavailable: '+e.message;}
}
async function saveAutomationMaster(){
 const body={
  mode:$('automationMode').value,risk_level:$('automationRiskLevel').value,
  paper_capital:$('automationPaperCapital').value,protected_pct:$('automationProtectedPct').value,
  profit_lock_pct:$('automationProfitLock').value,compound_pct:$('automationCompoundPct').value,
  reserve_profit_pct:$('automationReservePct').value};
 try{
  await api('automation/config','POST',body);
  await loadAutomationStatus(true);
 }catch(e){$('automationMasterStatus').textContent='Master plan was not saved: '+e.message;}
}
async function automationEngineAction(engine,action){
 const m=automationSnapshot?.master;
 if(action==='start'){
  const mode=m?.mode||'observe';
  if(!confirm('Start '+engine+' in '+mode.toUpperCase()+
   ' mode? Paper mode is experimental only. It can model losses, fees and simulated positions; it cannot send real orders.'))return;
 }
 if(action==='stop'&&!confirm('Stop '+engine+' monitoring? Existing PAPER positions will remain recorded until reconciled.'))return;
 try{
  const mode=m?.mode||'observe';
  const body=action==='start'?{confirmation:mode==='paper'?'START PAPER':'START OBSERVE'}:{};
  await api('automation/'+engine+'/'+action,'POST',body);
  await loadAutomationStatus();
 }catch(e){$('automationReason_'+engine).textContent='Action blocked: '+e.message;}
}
async function resetAutomationEmergency(){
 if(!confirm('Clear the Emergency Stop latch? All engines will remain PAUSED; you must restart each explicitly.'))return;
 try{
  await api('automation/emergency/reset','POST',{confirmation:'RESET EMERGENCY'});
  await loadAutomationStatus();
 }catch(e){$('automationMasterStatus').textContent='Reset blocked: '+e.message;}
}
async function api(path,method='GET',data){
 if(!authenticated||!base)throw Error('Sign in to EdgePilot first');
 let r=await fetch(base+'/api/'+path,{method,credentials:'same-origin',cache:'no-store',
  headers:{'Content-Type':'application/json','X-Edge-CSRF':csrf},
  body:data?JSON.stringify(data):undefined});
 let j=await r.json();
 if(r.status===401){clearLogin();throw Error('Your secure session expired. Sign in again.');}
 if(r.status===403&&j.error==='Invalid request verification token') {
  const refresh=await fetch(base+'/api/session',{credentials:'same-origin',cache:'no-store'});
  if(refresh.ok){csrf=(await refresh.json()).csrf;return api(path,method,data);}
 }
 if(!r.ok)throw Error(j.error||'HTTP '+r.status);
 return j;
}
function alertError(e){alert(e.message||String(e));}
function clearLogin(){authenticated=false;csrf='';snap=null;$('auth').value='';if($('publicApiSecret'))$('publicApiSecret').value='';$('setup').classList.remove('hidden');$('mode').textContent='DISCONNECTED';}
function signedIn(csrfToken){base=location.origin;csrf=csrfToken;authenticated=true;$('auth').value='';$('setup').classList.add('hidden');$('mode').textContent='SECURE SESSION';}
async function connect(){
 const requested=$('url').value.replace(/\/$/,'');
 if(requested!==location.origin){alert('For security, sign in through this page’s own HTTPS address, not another backend URL.');return;}
 const credential=$('auth').value;
 try{
  const r=await fetch(location.origin+'/api/login',{method:'POST',credentials:'same-origin',cache:'no-store',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({accessToken:credential})});
  const j=await r.json();
  if(!r.ok)throw Error(j.error||'Login failed');
  signedIn(j.csrf);
  await refresh();
 }catch(e){alertError(e);}finally{$('auth').value='';}
}
async function restoreSession(){
 base=location.origin;
 try{
  const r=await fetch(base+'/api/session',{credentials:'same-origin',cache:'no-store'});
  if(!r.ok){clearLogin();return;}
  const j=await r.json();signedIn(j.csrf);await refresh();
 }catch(e){clearLogin();}
}
async function refresh(){try{snap=await api('dashboard');let b=snap.broker,s=snap.settings;
try {let l=await api('ledger');$('ledgerPnl').textContent=money(l.realizedPnl);$('realizedHome').textContent=money(l.realizedPnl);$('ledgerCost').textContent=money(l.openCostBasis);$('ledgerStatus').textContent=l.warning; $('salePrompts').textContent=(l.pendingDecisions||[]).length+' manual-sale decisions pending (workflow not yet active).';}catch(e){$('ledgerStatus').textContent='Ledger unavailable: '+e.message;}
$('profileLabel').value=s.profile_label||'My EdgePilot';$('portfolioValue').textContent=b?money(b.balance):'—';$('holdingsCount').textContent=b?String(b.positionCount):'—';renderHoldings(b?.holdings||[]);$('balance').textContent=b?money(b.balance):'—';$('balanceMode').textContent=b?`Risk source: ${b.balanceSource==='independent'?'Assigned EdgePilot '+money(b.effectiveBalance):'Live Public '+money(b.effectiveBalance)}`:'Risk source: unavailable';$('balanceAlert').classList.toggle('hidden',!b?.requiresBalanceReset);$('balanceAlert').textContent=b?.balanceAlert||'';$('protected').textContent=b?money(b.protectedAmount):'—';$('riskbudget').textContent=b?money(b.riskBudget):'—';$('remaining').textContent=b?money(b.remainingToRisk):'—';$('power').textContent=b?money(b.cashBuyingPower):'—';
$('fundsAccountValue').textContent=b?money(b.balance):'—';$('fundsBuyingPower').textContent=b?money(b.cashBuyingPower):'—';
$('accountCashBuyingPower').textContent=b?money(b.cashBuyingPower):'—';
$('accountHoldingsValue').textContent=b?money(b.positionsExposure):'—';
$('accountSnapshotNote').textContent=b
 ? 'Refreshed from Public at '+new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})+'. Buying power is not additional account value.'
 : 'Public account data is unavailable. Check Settings → Public Brokerage Connection.';$('brokerError').textContent=snap.brokerError||'';
$('barfill').style.width=b&&Number(b.balance)?Math.min(100,100*Number(b.riskBudget)/Number(b.balance))+'%':'0%';$('allocationText').textContent=b?`Existing positions: ${money(b.positionsExposure)} · Open broker buys: ${money(b.brokerOpenBuyExposure)} · Local reserved: ${money(b.unreconciledLocal)}`:'Broker not yet linked';
$('livestate').textContent=s.live_armed==='1'?'ARMED':'DISARMED';$('livestate').className='pill '+(s.live_armed==='1'?'on':'');
$('balanceSource').value=s.balance_source||'public';$('independentBalance').value=s.independent_balance||'10.00';balanceSourceChanged();$('holdingsScope').value=s.holdings_scope||'allocated_only';$('cap').value=s.spend_cap;$('pct').value=s.protected_pct;$('single').value=s.per_trade_cap;$('daily').value=s.daily_loss_cap;$('autonomy').checked=s.autonomous==='1';$('microEnabled').checked=s.micro_enabled==='1';$('stockEdge').value=s.micro_stock_min_edge_pct||'0.50';$('predEdge').value=s.micro_prediction_min_edge_pct||'3.00';$('microNet').value=s.micro_min_net_dollars||'0.05';$('microTrades').value=s.micro_max_trades_day||'5';
$('activity').innerHTML=(snap.activity||[]).map(x=>`<div class="log">${esc(x.ts.slice(0,16))} · ${esc(x.message)}</div>`).join('')||'No activity yet';$('orders').innerHTML=(snap.orders||[]).map(x=>`<div class="log">${esc(x.side)} ${esc(x.symbol)} ×${x.qty} @ ${esc(x.limit_price)}<br><span class="muted">${esc(x.state)} · ${esc(x.created.slice(0,16))}</span></div>`).join('')||'No orders yet';
await loadPerformance();await loadAutomationStatus(true);$('watchList').innerHTML=(snap.watch||[]).map(w=>`<div class="rule">${esc(w.symbol)} · buy ≤ ${esc(w.buy_below)} / sell ≥ ${esc(w.sell_above)} <button onclick="toggleRule('${esc(w.id)}')">${w.enabled?'Disable':'Enable'}</button></div>`).join('');
if(s.account_id){$('account').innerHTML=`<option value="${esc(s.account_id)}">${esc(s.account_id)}</option>`}else{$('account').innerHTML='<option value="">Choose account</option>'}
}catch(e){$('brokerError').textContent=e.message;}}

// Public API secret is entered transiently, never included in dashboard JSON or browser storage.
async function loadPublicKeyStatus(){
 const el=$('publicCredentialStatus');if(!el || !authenticated)return;
 try{
   const r=await api('broker/credentials/status');
   el.textContent=(r.configured?'Public key configured ('+r.source+').':'Public key not configured.')+
     (r.encryptionReady?' Encryption enabled.':' Server encryption key not ready.')+
     (r.usable?' Ready for a read-only connection test.':'');
 }catch(e){el.textContent='Unable to check Public connection: '+e.message;}
}
async function savePublicKey(){
 const field=$('publicApiSecret'), el=$('publicCredentialStatus');
 const secret=field.value.trim();
 if(secret.length<20){el.textContent='Enter the Public API secret (not your app sign-in token).';return;}
 if(!confirm('Save this Public API credential to the encrypted EdgePilot server? It may authorize brokerage trading outside this app.'))return;
 try{
  await api('broker/credentials','POST',{secret});
  el.textContent='Key saved. Next tap Test connection. Real trading remains disabled.';
  await loadPublicKeyStatus();
  await refresh();
 }catch(e){el.textContent='Could not save key: '+e.message;}
 finally{field.value='';}
}
async function testPublicKey(){
 const el=$('publicCredentialStatus');el.textContent='Testing Public access (read-only)…';
 try{
  const r=await api('connection/verify');
  el.textContent='Public connection test: '+JSON.stringify(r,null,2);
 }catch(e){el.textContent='Public connection test failed: '+e.message;}
}
async function removePublicKey(){
 if(!confirm('Disconnect Public and clear the saved API secret? Your selected brokerage account will be reset.'))return;
 const el=$('publicCredentialStatus');
 try{await api('broker/credentials','DELETE');$('publicApiSecret').value='';await loadPublicKeyStatus();await refresh();}
 catch(e){el.textContent='Could not disconnect: '+e.message;}
}

async function loadAccounts(){try{let d=await api('accounts');$('account').innerHTML='<option value="">Choose account</option>'+d.accounts.map(x=>`<option value="${esc(x.accountId)}">${esc(x.accountType)} · ${esc(x.accountId)}</option>`).join('');}catch(e){alertError(e)}}
async function saveSettings(){try{let body={spend_cap:$('cap').value,protected_pct:$('pct').value,per_trade_cap:$('single').value,daily_loss_cap:$('daily').value};if($('account').value&&$('account').value!==(snap?.settings.account_id||''))body.account_id=$('account').value;await api('settings','POST',body);$('saveResult').textContent='Saved. Live trading disarmed if allocation/account changed.';await refresh();}catch(e){alertError(e)}}
async function changeAutonomy(){let on=$('autonomy').checked;try{if(on&&!confirm('Store fully autonomous preference? Automated execution is NOT active in this prototype.')){$('autonomy').checked=false;return;}await api('settings','POST',{autonomous:on?'1':'0',...(on?{confirmation:'ENABLE AUTONOMY'}:{})});await refresh();}catch(e){$('autonomy').checked=!on;alertError(e)}}
async function arm(){if(!confirm('Arm REAL-money manual trading? Loss of capital is possible.'))return;try{await api('settings','POST',{live_armed:'1',confirmation:'ARM LIVE TRADING'});await refresh();}catch(e){alertError(e)}}
async function emergency(){try{await api('disarm','POST',{});await refresh();await loadAutomationStatus();alert('Global Emergency Stop latched. All engines paused; existing broker orders are NOT canceled. Manual reset required.');}catch(e){alertError(e)}}
// v0.19.14: manually refreshed 15-minute event-details snapshots (no trade path).
async function loadFifteenMinuteMarkets(){
 const status=$('fifteenStatus'), list=$('fifteenList');
 status.textContent='Checking open Public 15-minute windows…';list.textContent='';
 try{
  const d=await api('markets/15-minute');
  if(!d.connected){status.textContent=d.note||'Connect Public in Settings first.';return;}
  const count=(d.events||[]).length;
  const captured=new Date(d.capturedAt);
  status.textContent=`${count} validated active windows at ${Number.isFinite(captured.getTime())?captured.toLocaleTimeString():'the scan time'}. Prices are captured snapshots, not live streaming quotes. ${d.coverage?.skippedInvalid||0} incomplete/closed entries omitted. No trades placed.`;
  if(!count){list.textContent='No eligible open windows returned. Try Refresh later; the API may be empty or some quotes may be incomplete.';return;}
  list.innerHTML=d.events.map(m=>{
   const secs=Math.max(0,Number(m.secondsRemainingAtCapture)||0);
   const left=`${Math.floor(secs/60)}m ${secs%60}s at capture`;
   const side=(label,c)=>`<div class="rule"><b>${label}</b><br><small>${esc(c.symbol)}<br>Bid ${esc(c.bid)} · Ask ${esc(c.ask)} · Spread ${esc(c.spread)}<br>Illustrative break-even ${esc(c.illustrativeBreakEvenPct)}%</small></div>`;
   return `<div class="market"><div class="row"><b>${esc(m.title||m.series)}</b><span class="pill">${esc(left)}</span></div><p class="muted">${esc(m.eventSymbol)}<br>${esc(m.target)}<br>Closes ${esc(new Date(m.closeTime).toLocaleTimeString())}</p>${side('UP / YES',m.yes)}${side('DOWN / NO',m.no)}${(m.warnings||[]).map(w=>`<p class="warn">${esc(w)}</p>`).join('')}</div>`;
  }).join('');
 }catch(e){status.textContent='15-minute scan unavailable: '+(e.message||String(e));list.textContent='';}
}

async function loadMarkets(){try{let d=await api('markets');$('marketList').innerHTML=(d.events||[]).map(m=>`<div class="market"><b>${esc(m.title)}</b><p class="muted">${esc(m.symbol)} · volume ${esc(m.volume)}</p><button onclick="pickEvent('${esc(m.symbol)}')">Explore</button></div>`).join('')}catch(e){alertError(e)}}
function pickEvent(event){$('event').value=event;tab('markets');loadEvent()}
async function loadEvent(){try{let d=await api('event/'+encodeURIComponent($('event').value));$('contractList').innerHTML=(d.outcomes||[]).flatMap(o=>(o.contracts||[]).map(c=>`<div class="rule">${esc(o.title||o.name||'Outcome')}<br><small>${esc(c.symbol)} · bid ${esc(c.bid)} / ask ${esc(c.ask)}</small><br><button onclick="pickContract('${esc(d.eventSymbol)}','${esc(c.symbol)}','${esc(c.ask)}')">Set order</button></div>`)).join('')||'No contracts returned.'}catch(e){alertError(e)}}
function pickContract(e,c,p){$('tradeEvent').value=e;$('tradeSymbol').value=c;if(Number(p)>0)$('price').value=p;tab('trade')}
function tradeForm(){return {event:$('tradeEvent').value,symbol:$('tradeSymbol').value,side:$('side').value,qty:Number($('qty').value),price:$('price').value}}
async function preview(){try{let r=await api('order/preview','POST',tradeForm());$('previewOut').innerHTML=`<p>Public preflight: estimated cost <b>${money(r.cost)}</b><br><small>${esc(JSON.stringify(r.preflight).slice(0,700))}</small></p>`;$('confirmBox').classList.remove('hidden')}catch(e){$('confirmBox').classList.add('hidden');alertError(e)}}
async function placeOrder(){if(!confirm('Submit real '+$('side').value+' order to Public now?'))return;try{let r=await api('order/submit','POST',{...tradeForm(),confirmation:'PLACE LIVE ORDER'});$('confirmBox').classList.add('hidden');alert('Submitted, NOT confirmed filled: '+r.orderId);await refresh()}catch(e){alertError(e)}}
async function addWatch(){try{await api('watch','POST',{event:$('watchEvent').value,symbol:$('watchSymbol').value,quantity:Number($('watchQty').value),fair_pct:$('fair').value,buy_below:$('buyBelow').value,sell_above:$('sellAbove').value});await refresh()}catch(e){alertError(e)}}
async function toggleRule(id){try{await api('watch/'+encodeURIComponent(id)+'/toggle','POST',{});await refresh()}catch(e){alertError(e)}}
async function scan(){try{let d=await api('opportunities');$('scans').innerHTML=(d.opportunities||[]).map(x=>`<div class="rule">${esc(x.rule.symbol)} — ${esc(x.suggestion||x.error)}<br>Bid ${esc(x.bid)}, Ask ${esc(x.ask)}, estimated edge ${esc(x.netEdge)}</div>`).join('')||'No enabled watch rules.';}catch(e){alertError(e)}}

async function saveHoldingsScope(){try{const scope=$('holdingsScope').value;let message=scope==='existing_allowed'?'Allow future EdgePilot equity strategies to consider stocks and ETFs you already own? This does NOT enable trading now.':'Restrict future equity strategies to EdgePilot-owned holdings?';if(!confirm(message))return;await api('settings','POST',{holdings_scope:scope});$('scopeResult').textContent='Saved. Live trading disarmed; equity trading remains unavailable in this prototype.';await refresh();}catch(e){alertError(e)}}

function balanceSourceChanged(){ $('independentControls').classList.toggle('hidden',$('balanceSource').value!=='independent'); }
async function saveBalanceSource(){try{const mode=$('balanceSource').value;const body={balance_source:mode};if(mode==='independent')body.independent_balance=$('independentBalance').value; if($('account').value&&$('account').value!==(snap?.settings.account_id||''))body.account_id=$('account').value;await api('settings','POST',body);$('balanceSaveResult').textContent='Saved. Live orders disarmed until explicitly reauthorized.';await refresh();}catch(e){alertError(e)}}

async function saveProfile(){try{await api('settings','POST',{profile_label:$('profileLabel').value.trim()});$('profileResult').textContent='Personal profile saved.';await refresh()}catch(e){alertError(e)}}
async function disconnect(){
 if(authenticated){try{await fetch(location.origin+'/api/logout',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'X-Edge-CSRF':csrf}});}catch(e){}}
 clearLogin();window.scrollTo(0,0);
}

async function saveMicro(){try{await api('settings','POST',{micro_enabled:$('microEnabled').checked?'1':'0',micro_stock_min_edge_pct:$('stockEdge').value,micro_prediction_min_edge_pct:$('predEdge').value,micro_min_net_dollars:$('microNet').value,micro_max_trades_day:$('microTrades').value});$('microSaveResult').textContent='Saved. Live trading remains disabled.';await refresh()}catch(e){alertError(e)}}
async function evaluateMicro(){try{let r=await api('micro/evaluate','POST',{market:$('microMarket').value,quantity:$('microQty').value,entry_price:$('microEntry').value,win_exit_price:$('microWin').value,loss_exit_price:$('microLoss').value,success_probability_pct:$('microProb').value,total_fees:$('microFees').value,total_slippage:$('microSlip').value});$('microResult').innerHTML=`<b>Expected net result: ${money(r.expectedNetValue)}</b><br>Winning outcome: ${money(r.netWinningGain)} / Losing outcome: ${money(r.netLosingResult)}<br>Round-trip costs: ${money(r.roundTripCost)}<br>Passes modeled economic screen: ${r.passesEconomicScreen?'YES':'NO'}<br><small>${esc(r.warning)}</small>`}catch(e){alertError(e)}}

// Chart and appearance are strictly presentation features; never modify trade/risk calculations.
let chartPoints=[],period='1M',selectedTheme='system';
const prefersDark=window.matchMedia('(prefers-color-scheme: dark)');
function setTheme(value){if(!['system','light','dark'].includes(value))return;selectedTheme=value;try{localStorage.setItem('edgepilot-theme',value)}catch(e){}applyTheme()}
function applyTheme(){const actual=selectedTheme==='system'?(prefersDark.matches?'dark':'light'):selectedTheme;document.documentElement.dataset.theme=actual;document.querySelector('meta[name="theme-color"]')?.setAttribute('content',actual==='dark'?'#0c1423':'#f5f7fb');document.querySelectorAll('[data-theme-choice]').forEach(b=>b.classList.toggle('selected',b.dataset.themeChoice===selectedTheme));if($('themeStatus'))$('themeStatus').textContent='Selected: '+selectedTheme.charAt(0).toUpperCase()+selectedTheme.slice(1);renderChart()}
try{selectedTheme=localStorage.getItem('edgepilot-theme')||'system'}catch(e){}
if(!['system','light','dark'].includes(selectedTheme))selectedTheme='system';
prefersDark.addEventListener?.('change',()=>{if(selectedTheme==='system')applyTheme()});
function setPeriod(p){period=p;document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('selected',b.dataset.period===p));renderChart()}
function renderHoldings(items){const el=$('holdingsList');if(!el)return;el.replaceChildren();if(!items.length){el.textContent='No positions returned for this account.';return}items.slice().sort((a,b)=>Number(b.value)-Number(a.value)).slice(0,20).forEach(x=>{const row=document.createElement('div');row.className='asset-row';const left=document.createElement('div'),right=document.createElement('div');const name=document.createElement('b');name.textContent=x.symbol;const qty=document.createElement('div');qty.className='muted';qty.textContent=x.quantity+' units';left.append(name,qty);right.textContent=money(x.value);row.append(left,right);el.append(row)})}
async function loadPerformance(){try{const r=await api('performance/history');chartPoints=(r.points||[]).map(x=>({time:Date.parse(x.ts),value:Number(x.value)})).filter(p=>Number.isFinite(p.time)&&Number.isFinite(p.value));renderChart()}catch(e){chartPoints=[];renderChart();$('chartNote').textContent='Historical balance data unavailable: '+e.message}}
function renderChart(){const svg=$('portfolioChart');if(!svg)return;const width=360,height=210,pad={l:10,r:10,t:18,b:22};svg.replaceChildren();document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('selected',b.dataset.period===period));const now=Date.now(),days={'1D':1,'1W':7,'1M':30,'3M':90,'1Y':365,'ALL':Infinity}[period];const cutoff=now-days*864e5;const points=chartPoints.filter(p=>p.time>=cutoff);const message=(v)=>{const t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x','180');t.setAttribute('y','108');t.setAttribute('text-anchor','middle');t.setAttribute('fill','currentColor');t.setAttribute('opacity','.65');t.setAttribute('font-size','12');t.textContent=v;svg.append(t)};
if(points.length<2){message('Not enough snapshots for this range');$('valueChange').textContent='—';$('percentChange').textContent='—';$('portfolioChange').textContent='History collecting · no period comparison';$('chartNote').textContent='Only actual recorded account snapshots are plotted. Refresh periodically to build history.';return}
const values=points.map(p=>p.value),lo=Math.min(...values),hi=Math.max(...values),range=Math.max(0.01,hi-lo),xmin=points[0].time,xmax=points[points.length-1].time,dx=Math.max(1,xmax-xmin);const x=p=>pad.l+(p.time-xmin)/dx*(width-pad.l-pad.r),y=p=>pad.t+(hi-p.value+.12*range)/(1.24*range)*(height-pad.t-pad.b);
const make=(tag,attrs)=>{const el=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v)));svg.append(el);return el};[.25,.5,.75].forEach(fr=>make('line',{x1:pad.l,x2:width-pad.r,y1:pad.t+fr*(height-pad.t-pad.b),y2:pad.t+fr*(height-pad.t-pad.b),stroke:'currentColor','stroke-opacity':'.1'}));const line=points.map((p,i)=>(i?'L':'M')+x(p).toFixed(1)+','+y(p).toFixed(1)).join(' ');const diff=points.at(-1).value-points[0].value;const positive=diff>=0;const color=positive?'var(--accent)':'var(--negative)';make('path',{d:line,stroke:color,'stroke-width':2.8,fill:'none','stroke-linejoin':'round','stroke-linecap':'round'});make('circle',{cx:x(points.at(-1)),cy:y(points.at(-1)),r:4.2,fill:color});$('valueChange').textContent=(positive?'+':'−')+money(Math.abs(diff));$('valueChange').className='metric '+(positive?'delta-pos':'delta-neg');const pct=points[0].value?diff/points[0].value*100:null;$('percentChange').textContent=pct===null?'—':(pct>=0?'+':'')+pct.toFixed(2)+'%';$('percentChange').className='metric '+(positive?'delta-pos':'delta-neg');$('portfolioChange').textContent=(positive?'+':'−')+money(Math.abs(diff))+(pct===null?'':` (${pct>=0?'+':''}${pct.toFixed(2)}%)`)+' · '+period;$('portfolioChange').className=positive?'delta-pos':'delta-neg';$('chartNote').textContent='Recorded Public account value, not pure trading performance. Deposits, withdrawals and outside trades can affect this chart.'}
applyTheme();setPeriod('1M');

// v0.19.1 — read-only synchronization; no broker trades or position attribution.
async function runBrokerSync(){const el=$('syncStatus');el.textContent='Synchronizing Public records…';try{const out=await api('sync/run','POST',{});el.textContent=`${out.status}: ${out.importedTransactions} newly captured transactions; ${out.openAlerts} alerts. No executions imported into trading ledger.`;await loadSyncStatus()}catch(err){el.textContent='Sync failed: '+err.message}}
async function loadSyncStatus(){
 const action=$('syncAcknowledgeAll');
 action.disabled=true;
 try{
  const d=await api('sync/status');
  $('syncStatus').textContent=d.lastSync?`Last sync: ${d.lastSync.ts} · ${d.totalTransactionsCaptured} broker transactions saved · attribution not verified`:'No completed sync. Tap Sync now.';
  const count=Number(d.openAlertCount??(d.alerts||[]).length);
  $('syncAlertCount').textContent=`${count} outstanding ${count===1?'alert':'alerts'}`+(count>(d.alerts||[]).length?` (showing latest ${(d.alerts||[]).length})`:'');
  action.disabled=count===0;
  const box=$('syncAlerts');box.replaceChildren();
  (d.alerts||[]).forEach(a=>{
   const item=document.createElement('div');item.className='rule';
   const title=document.createElement('p');title.textContent=a.message;
   const btn=document.createElement('button');btn.textContent='Acknowledge';
   btn.onclick=async()=>{
    if(!confirm('Acknowledge this informational alert? No repurchase or trading permission is granted.'))return;
    btn.disabled=true;
    try{await api('sync/alerts/'+a.id+'/acknowledge','POST',{});await loadSyncStatus()}
    catch(e){$('syncStatus').textContent='Acknowledgement failed: '+e.message;btn.disabled=false}
   };
   item.append(title,btn);box.append(item);
  });
 }catch(e){
  $('syncStatus').textContent='Synchronization status unavailable: '+e.message;
  $('syncAlertCount').textContent='Alert count unavailable';
 }
}
async function acknowledgeAllSyncAlerts(){
 const btn=$('syncAcknowledgeAll');
 if(btn.disabled)return;
 const countText=$('syncAlertCount').textContent;
 if(!confirm('Acknowledge ALL '+countText+' for this selected Public account? This only marks notices as reviewed. It does not verify sales, allow repurchases, delete records, or enable orders.'))return;
 btn.disabled=true;
 try{
  const r=await api('sync/alerts/acknowledge-all','POST',{});
  await loadSyncStatus();
  $('syncStatus').textContent=`Acknowledged ${r.acknowledgedCount} alerts for the selected Public account. Historical records retained; no trading actions.`;
 }catch(e){
  $('syncStatus').textContent='Acknowledge All failed: '+e.message;
  await loadSyncStatus();
 }
}

// v0.19.2 — order details auditing (read only; never post P&L).
async function runOrderAudit(){const el=$('orderAuditStatus');el.textContent='Fetching Public order details…';try{const r=await api('orders/audit/run','POST',{});el.textContent=`Observed ${r.ordersObserved} orders; ${r.newTrades} new confirmed trade IDs. Actual fees/origins remain unverified; live trading disabled.`;await loadOrderAudit()}catch(e){el.textContent='Audit failed: '+e.message}}
async function loadOrderAudit(){try{const r=await api('orders/audit');$('orderAuditStatus').textContent=r.lastRun?`Last audit: ${r.lastRun.ts} · ${r.orders.length} recently observed orders · ${r.trades.length} observed executions · READ ONLY`:'No order audit recorded.';const out=$('orderAuditDetails');out.replaceChildren();for(const a of (r.alerts||[]).slice(0,10)){const row=document.createElement('div');row.className='rule';row.textContent=a.kind+': '+a.message;out.append(row)}for(const t of (r.trades||[]).slice(0,10)){const row=document.createElement('div');row.className='log';row.textContent=`${t.symbol} ${t.side} ${t.quantity} @ ${t.price} · ${t.origin} · fees ${t.fees_status}`;out.append(row)}}catch(e){$('orderAuditStatus').textContent='Order audit unavailable: '+e.message}}

// v0.19.3 — on-demand, opt-in AI analysis; no broker order capabilities.
async function loadAI(){try{const s=await api('ai/status');$('aiEnabled').checked=s.enabled;$('aiBudget').value=s.monthlyBudgetUsd;$('aiStatus').textContent=`${s.enabled?'Enabled':'Disabled'} · Provider key ${s.credentialConfigured?'configured':'missing'} · Local reserved ${money(s.estimatedBudgetReservedUsd)} / ${money(s.monthlyBudgetUsd)} for ${s.month}. This is not an API billing cap.`;const h=await api('ai/history');const out=$('aiHistory');out.replaceChildren();for(const a of h.history){const row=document.createElement('div');row.className='rule';const heading=document.createElement('b');heading.textContent=`${a.market} ${a.asset}: ${a.question}`;const p=document.createElement('p');p.className='muted';p.style.whiteSpace='pre-wrap';p.textContent=a.reply;row.append(heading,p);out.append(row);}if(!h.history.length)out.textContent='No AI research questions yet.'}catch(e){$('aiStatus').textContent=e.message;}}
async function saveAISettings(){try{if($('aiEnabled').checked&&!confirm('Enable external OpenAI analysis? Any questions and context you submit will be sent to your configured AI provider and may incur separate API charges.'))return;await api('settings','POST',{ai_enabled:$('aiEnabled').checked?'1':'0',ai_monthly_budget_usd:$('aiBudget').value});await loadAI();}catch(e){alertError(e)}}
async function askEdgeAI(){const el=$('aiResponse');el.textContent='Requesting analysis…';try{const r=await api('ai/analyze','POST',{market:$('aiMarket').value,asset:$('aiAsset').value,context:$('aiContext').value,question:$('aiQuestion').value});el.textContent=r.answer+'\n\nAI interpretation only. No trades placed.';await loadAI()}catch(e){el.textContent='AI request stopped: '+e.message;}}

// v0.19.4: broker quote lookup and explicit AI transfer consent. No automated orders.
let currentResearchSnapshot=null;
async function loadResearchSnapshot(){const el=$('researchSnapshot');el.textContent='Fetching current Public quote…';currentResearchSnapshot=null;
try{const r=await api('research/snapshot','POST',{market:$('researchMarket').value,symbol:$('researchSymbol').value.trim(),event:$('researchEvent').value.trim()});currentResearchSnapshot=r.snapshot;const s=r.snapshot;
el.textContent=JSON.stringify({source:s.source,market:s.market,symbol:s.symbol,event:s.event,capturedAt:s.capturedAt,bid:s.bid,ask:s.ask,spread:s.spread,spreadPct:s.spreadPctOfAsk,knownStale:s.knownStale,quoteAgeSeconds:s.quoteAgeSeconds,volume:s.volume,openForTrading:s.openForTrading,completeQuote:s.completeTopOfBook,warnings:s.riskWarning},null,2);
}catch(e){el.textContent='Quote unavailable: '+e.message;}}
async function askSnapshotAI(){const out=$('researchAIResponse');if(!currentResearchSnapshot){out.textContent='Fetch and inspect a quote first.';return;}
if(!confirm('Allow EdgePilot to retrieve a fresh Public market quote and send its market details and your question to OpenAI? No account IDs, secrets, or portfolio positions will be shared. API billing applies.'))return;
out.textContent='Updating quote and requesting optional AI analysis…';try{const r=await api('research/analyze-snapshot','POST',{market:$('researchMarket').value,symbol:$('researchSymbol').value.trim(),event:$('researchEvent').value.trim(),question:$('researchQuestion').value.trim(),consent:true});out.textContent=r.answer+'\n\nRead-only research. Snapshot at '+r.capturedAt+'. No trade placed.';await loadAI();}catch(e){out.textContent='Analysis unavailable: '+e.message}}


// v0.19.5: research scanner. HTML text is escaped; no trade action is exposed.
async function loadScannerConfig(){try{const r=await api('scanner/config');$('scannerSymbols').value=r.symbols;$('discoveryMode').value=r.mode||'automatic';$('equityPerScan').value=r.equityPerScan||15;$('eventsPerScan').value=r.eventsPerScan??5}catch(e){$('scannerStatus').textContent=e.message}}
async function saveScannerSymbols(){try{const r=await api('scanner/config','POST',{symbols:$('scannerSymbols').value,mode:$('discoveryMode').value,equityPerScan:Number($('equityPerScan').value),eventsPerScan:Number($('eventsPerScan').value)});$('scannerStatus').textContent='Discovery settings saved: '+r.mode}catch(e){alertError(e)}}
async function runOpportunityScanner(){const out=$('scannerCandidates');out.replaceChildren();$('scannerStatus').textContent='Discovering markets and requesting a bounded sample of broker quotes…';
try{const d=await api('scanner/run','POST',{});$('scannerStatus').textContent=`Mode: ${d.mode}. ${d.candidates.length} candidates, ${d.unavailable.length} unavailable. ${d.mode==='watchlist' ? d.coverage.equitiesSampled+' watchlist stocks checked ('+d.coverage.watchlistSymbols+' configured)' : d.coverage.equitiesSampled+' stocks sampled from '+d.coverage.eligibleEquitiesReported+' broker-listed'}; ${d.coverage.eventsReviewed} prediction events. Research only; no trades.`;
for(const x of d.candidates){const div=document.createElement('div');div.className='rule';const title=document.createElement('b');title.textContent=`${x.symbol} · ${x.market} · quality ${x.qualityScore}/100`;
const detail=document.createElement('p');detail.className='muted';detail.textContent=`Bid ${x.bid} · Ask ${x.ask} · ${x.classification}${x.expectedNetValue===null?'': ' · illustrative expected net value $'+x.expectedNetValue}`;
const reason=document.createElement('small');reason.textContent=x.reasons.join(' • ');div.append(title,detail,reason);out.append(div)}
for(const x of d.unavailable){const div=document.createElement('div');div.className='rule warn';div.textContent=x.symbol+' — '+x.reason;out.append(div)}
if(!d.candidates.length&&!d.unavailable.length)out.textContent='No candidates available.';
}catch(e){$('scannerStatus').textContent='Scan failed: '+e.message}}

// v0.19.7: research-only, user-provided historical bars. Not an order signal.
async function runHistoricalStudy(){const out=$('studyResult');out.textContent='Evaluating historical bars…';try{const r=await api('predictive/backtest','POST',{csv:$('historyCsv').value,lookback:Number($('studyLookback').value),hold:Number($('studyHold').value),costBps:Number($('studyCost').value),trainingPct:Number($('studySplit').value)});const fmt=x=>x===null?'Insufficient trades':String(x);out.textContent=`Historical study (${r.bars} daily bars)\nTraining trades: ${r.training.trades} | net compounded: ${r.training.compoundedNetReturnPct}%\nOut-of-sample trades: ${r.outOfSample.trades} | win rate: ${fmt(r.outOfSample.winRatePct)}% | net compounded: ${r.outOfSample.compoundedNetReturnPct}% | maximum drawdown: ${r.outOfSample.maxDrawdownPct}%\nAssumed round-trip costs: ${r.assumptions.roundTripCostBps} bps\n\n${r.warning}`;}catch(e){out.textContent='Historical study unavailable: '+e.message}}

// v0.19.8: research-only historical Public API study; backend validates and caches broker data.
async function runPublicHistoricalStudy(){
 const out=$('publicHistoryStatus');out.textContent='Retrieving historical bars and running study…';
 try{
  const r=await api('predictive/public-history','POST',{symbol:$('publicHistorySymbol').value.trim().toUpperCase(),period:$('publicHistoryPeriod').value,refresh:$('publicHistoryRefresh').checked,lookback:Number($('studyLookback').value),hold:Number($('studyHold').value),costBps:Number($('studyCost').value),trainingPct:Number($('studySplit').value)});
  out.textContent=`${r.symbol} • ${r.bars} daily bars (${r.firstBarDate} – ${r.lastBarDate}) • ${r.cached?'cache':'broker fetch'}\nTraining: ${r.training.trades} trades, ${r.training.compoundedNetReturnPct}% modeled compounded net return\nOut-of-sample: ${r.outOfSample.trades} trades, ${r.outOfSample.compoundedNetReturnPct}% modeled compounded net return, ${r.outOfSample.maxDrawdownPct}% max drawdown\nData fetched: ${r.fetchedAt}\n\n${r.warning}`;
 }catch(e){out.textContent='Historical data unavailable: '+e.message;}
}

// v0.19.9 — research-only chronological walk-forward evaluation.
async function runWalkForwardStudy(){
 const out=document.getElementById('walkForwardStatus');out.textContent='Running chronological validation…';
 const source=document.getElementById('walkSource').value;
 try{
  const body={source,trainingBars:Number(document.getElementById('walkTrain').value),testBars:Number(document.getElementById('walkTest').value),stepBars:Number(document.getElementById('walkTest').value),holdingDays:Number(document.getElementById('studyHold').value),costBps:Number(document.getElementById('studyCost').value),lookbacks:[3,5,10,20]};
  if(source==='public'){body.symbol=document.getElementById('publicHistorySymbol').value;body.period=document.getElementById('publicHistoryPeriod').value}
  else body.csv=document.getElementById('historyCsv').value;
  const r=await api('predictive/walk-forward','POST',body);
  const lines=[`${r.method} | ${r.bars} bars`,`${r.evaluatedWindows} evaluated windows; ${r.positiveWindows} positive windows`,
    `OOS trades ${r.outOfSample.trades} | net compounded ${r.outOfSample.compoundedReturnPct}% | max drawdown ${r.outOfSample.maxDrawdownPct}%`,
    `Assessment: ${r.researchReadiness}`,''];
  for(const f of r.folds){lines.push(`${f.testStartDate} – ${f.testEndDate}: ${f.status==='evaluated'?'lookback '+f.lookbackSelected+' days, '+f.test.trades+' trades, '+f.test.compoundedReturnPct+'% modeled net':'Insufficient training trades'}`)}
  lines.push('',...r.warnings.map(w=>'CAUTION: '+w),'',r.disclaimer);
  out.textContent=lines.join('\n');
 }catch(e){out.textContent='Validation unavailable: '+e.message}
}

// v0.19.10: broker account diagnostics are strictly read-only.
async function verifyBrokerConnection(){
 const el=$('connectionStatus');el.textContent='Testing authenticated Public account access (read-only)…';
 try {
  const r=await api('connection/verify');
  el.textContent=`Backend: ${r.backend} | Public: ${r.broker} | Accounts found: ${r.accountCount} | Selected account: ${r.selectedAccount} | Portfolio: ${r.portfolio}.\n${r.nextStep}\nNo trade was placed.`;
  if(r.broker==='verified'&&r.selectedAccount==='none')el.textContent+='\nNext: Settings → select account → Save settings.';
 } catch(e) { el.textContent='Connection check unavailable: '+e.message; }
}
// A hosted PWA connects to its own secure origin. Credentials are never persisted by this script.
if($('url') && location.protocol==='https:'){$('url').value=location.origin;restoreSession();}
