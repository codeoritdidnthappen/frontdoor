/* ===================== owner claim flow (same origin) =====================
   The design source carries this flow as a three-row stub. Here it is the real one:
   GET  /claim/places?q=          the catalogue search behind the result rows
   POST /claim                    submit, answering {claim_id, token} for this session only
   GET  /claim/<id>?token=        the review state; an approved claim opens the workspace
   GET  /claim/<id>/workspace?token=   what the public pin says today, plus incentives
   POST /claim/<id>/dispute       an owner's note; it never changes the public pin
   The claim record lives in sessionStorage, not localStorage: a claim token is a
   credential for one sitting, and the attested capture path proves itself with it.
   The design's own a11y machinery is kept intact — roving tabindex on the result rows,
   an inline error beside the control that blocks a submit, and a spoken announcement. */
let claimHits=[];
let claimSel=null;
let claimRecord=null;
const CLAIM_CHANNEL={email:'business_email', call:'listed_phone'};
function claimSessionLoad(){
  try{
    const raw=sessionStorage.getItem('entrymap.claim');
    if(!raw) return null;
    const rec=JSON.parse(raw);
    if(rec && rec.claim_id && rec.token) return rec;
  }catch(e){}
  return null;
}
function claimSessionSave(rec){
  claimRecord=rec;
  try{ sessionStorage.setItem('entrymap.claim', JSON.stringify({claim_id:rec.claim_id, token:rec.token})); }catch(e){}
}
function bizheadHTML(name, sub){
  return `<span class="cr-icon" aria-hidden="true">${iconSVG('store',20,'var(--purple-ink)')}</span>
     <span><span class="cr-name">${esc(name)}</span>
     <span class="cr-sub">${esc(sub||'')}</span></span>`;
}
function renderClaimHits(focusSel){
  const wrap=document.getElementById('claim-results');
  wrap.innerHTML='';
  wrap.setAttribute('role','radiogroup');
  wrap.setAttribute('aria-label','Choose the entrance you manage');
  if(!claimHits.length){
    wrap.innerHTML='<p class="sheet-p">No listings match that search yet.</p>';
    return;
  }
  claimHits.forEach((r,i)=>{
    const on = !!claimSel && claimSel.place_id===r.place_id;
    const b=document.createElement('button');
    b.className='claim-result'+(on?' sel':'');
    b.type='button';
    b.setAttribute('role','radio');
    b.setAttribute('aria-checked',on);
    b.tabIndex = on ? 0 : -1;             /* roving tabindex: the group is one tab stop */
    b.setAttribute('aria-label',`${r.name}, ${r.place_id}`);
    b.innerHTML=`<span class="cr-icon" aria-hidden="true">${iconSVG('store',20,'var(--purple-ink)')}</span>
      <span aria-hidden="true"><span class="cr-name">${esc(r.name)}</span>
      <span class="cr-sub">${esc(r.place_id)}</span></span>
      <span class="cr-mark" aria-hidden="true">&#10003;</span>`;
    b.addEventListener('click',()=>{claimSel=r;renderClaimHits(true);});
    b.addEventListener('keydown',e=>{
      const k=e.key;
      if(k!=='ArrowDown'&&k!=='ArrowRight'&&k!=='ArrowUp'&&k!=='ArrowLeft') return;
      e.preventDefault();
      const d=(k==='ArrowDown'||k==='ArrowRight')?1:-1;
      claimSel=claimHits[(i+d+claimHits.length)%claimHits.length];
      renderClaimHits(true);
    });
    wrap.appendChild(b);
  });
  if(focusSel){ const sel=wrap.querySelector('[aria-checked="true"]'); if(sel) sel.focus(); }
}
async function searchClaims(){
  const q=document.getElementById('claim-search').value.trim();
  if(q.length<2){ claimHits=[]; claimSel=null; renderClaimHits(); return; }
  try{
    const r=await fetch(CLAIM_API+'/places?q='+encodeURIComponent(q));
    const j=await r.json().catch(()=>({places:[]}));
    claimHits=j.places||[];
    if(claimSel && !claimHits.some(h=>h.place_id===claimSel.place_id)) claimSel=null;
    if(!claimSel && claimHits.length) claimSel=claimHits[0];
    renderClaimHits();
  }catch(e){ toast("Couldn't search listings"); }
}
function initClaimFind(){
  claimHits=[]; claimSel=null;
  renderClaimHits();
  searchClaims();   /* the field arrives with a search in it */
}
let claimSearchTimer=null;
document.getElementById('claim-search').addEventListener('input',()=>{
  clearTimeout(claimSearchTimer);
  claimSearchTimer=setTimeout(searchClaims, 180);
});
document.getElementById('btn-claim-continue').addEventListener('click',()=>{
  if(!claimSel){ toast('Pick a listing from the search results'); announceUI('Pick a listing from the search results.'); return; }
  document.getElementById('claim-bizhead').innerHTML=bizheadHTML(claimSel.name, claimSel.place_id);
  showScreen('claim-confirm');
});
document.querySelectorAll('input[name="claim-verify"]').forEach(rb=>rb.addEventListener('change',()=>{
  document.getElementById('vo-email').classList.toggle('sel',rb.value==='email'&&rb.checked);
  document.getElementById('vo-call').classList.toggle('sel',rb.value==='call'&&rb.checked);
  if(rb.value==='email') document.getElementById('vo-call').classList.remove('sel');
  else document.getElementById('vo-email').classList.remove('sel');
}));
/* B2b: a blocked submit is a real, perceivable refusal -- an inline error beside the
   control that blocks it, aria-invalid + aria-describedby on that control, focus moved to
   it, and an announcement. Clearing the box clears all of it again. */
function setUnavailable(el, on){
  if(!el) return;
  if(on) el.setAttribute('aria-disabled','true'); else el.removeAttribute('aria-disabled');
}
const claimAuthz=document.getElementById('claim-authz');
function setClaimAuthzError(on){
  const err=document.getElementById('claim-authz-err');
  err.classList.toggle('on',on);
  claimAuthz.setAttribute('aria-invalid',on?'true':'false');
  document.getElementById('claim-authz-label').setAttribute('data-invalid',on?'true':'false');
  if(on) claimAuthz.setAttribute('aria-describedby','claim-authz-err');
  else claimAuthz.removeAttribute('aria-describedby');
}
function syncClaimGate(){
  setUnavailable(document.getElementById('btn-claim-submit'), !claimAuthz.checked);
}
claimAuthz.addEventListener('change',()=>{ if(claimAuthz.checked) setClaimAuthzError(false); syncClaimGate(); });
syncClaimGate();
/* Only one channel asks the claimant to type anything. The listed-phone route calls the
   number the listing already carries -- a typed number would be input presenting itself
   as authority -- so there is no phone field to validate, and the inline error is about
   the work email alone. */
const claimEmail=document.getElementById('claim-email');
const claimEmailField=claimEmail.closest('.field');
function claimChannel(){
  const r=document.querySelector('input[name="claim-verify"]:checked');
  return r && r.value==='call' ? 'call' : 'email';
}
function setClaimContactError(on){
  const err=document.getElementById('claim-contact-err');
  err.classList.toggle('on', on);
  if(on){
    document.getElementById('claim-contact-err-text').textContent =
      "Add the work email we should send the link to, or choose to verify by phone.";
    claimEmail.setAttribute('aria-invalid','true');
    claimEmail.setAttribute('aria-describedby','claim-contact-err-text');
  } else {
    claimEmail.removeAttribute('aria-invalid');
    claimEmail.removeAttribute('aria-describedby');
  }
}
function syncClaimChannelUi(){
  const email=claimChannel()==='email';
  if(claimEmailField) claimEmailField.hidden=!email;
  if(!email) setClaimContactError(false);
}
claimEmail.addEventListener('input',()=>{ if(claimEmail.value.trim()) setClaimContactError(false); });
document.querySelectorAll('input[name="claim-verify"]').forEach(r=>r.addEventListener('change',()=>{ setClaimContactError(false); syncClaimChannelUi(); }));
syncClaimChannelUi();
document.getElementById('btn-claim-submit').addEventListener('click', async ()=>{
  if(!claimAuthz.checked){
    setClaimAuthzError(true);
    claimAuthz.focus();
    announceUI("Claim not submitted. Please confirm you're authorized to manage this listing.");
    return;
  }
  setClaimAuthzError(false);
  if(!claimSel){ toast('Pick a listing first'); return; }
  const ch=claimChannel();
  const val=claimEmail.value.trim();
  if(ch==='email' && !val){
    setClaimContactError(true);
    claimEmail.focus();
    announceUI('Claim not submitted. Add the work email we should send the link to.');
    return;
  }
  setClaimContactError(false);
  /* the typed address is input, never authority: the server verifies on the channel the
     listing itself carries, so only the channel choice and the role are sent with it. */
  const payload={place_id:claimSel.place_id, channel:CLAIM_CHANNEL[ch], role:document.getElementById('claim-role').value};
  if(ch==='email') payload.email=val;
  let r, j;
  try{
    r=await fetch(CLAIM_API,{method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    j=await r.json().catch(()=>({}));
  }catch(e){ toast("Couldn't submit the claim"); return; }
  if(!r.ok){ toast(j.detail || j.error || "Couldn't submit the claim"); return; }
  claimSessionSave(j);
  /* the confirmation names the channel it actually collected */
  const say=document.getElementById('claim-track-how');
  if(say) say.textContent = ch==='call'
    ? "We'll call the business's listed phone when your workspace is ready."
    : "We'll email you when your workspace is ready.";
  document.getElementById('track-pin').innerHTML=pinSVG('owner',38);
  showScreen('claim-track');
  refreshClaimTrack();
});
async function refreshClaimTrack(){
  const rec=claimRecord || claimSessionLoad();
  if(!rec) return;
  try{
    const r=await fetch(CLAIM_API+'/'+rec.claim_id+'?token='+encodeURIComponent(rec.token));
    const j=await r.json().catch(()=>({}));
    if(r.ok && j.status==='approved'){ openWorkspace(rec); }
  }catch(e){}
}
async function openWorkspace(rec){
  rec=rec || claimRecord || claimSessionLoad();
  if(!rec){ toast('No claim in this session'); return; }
  let r, j;
  try{
    r=await fetch(CLAIM_API+'/'+rec.claim_id+'/workspace?token='+encodeURIComponent(rec.token));
    j=await r.json().catch(()=>({}));
  }catch(e){ toast("Couldn't open the workspace"); return; }
  if(!r.ok){ toast(j.detail || 'Workspace is not ready yet'); return; }
  const pin=j.pin||{};
  document.getElementById('ws-bizhead').innerHTML=bizheadHTML(pin.name||'', pin.place_id||'');
  const tier=pin.owner_confirmed?'Owner-confirmed':(pin.state==='scanned_on_site'?'Scanned on-site':'Estimated');
  /* TICK-461: for a scanned pin the stamp label now says exactly what the tier says
     ("Scanned on-site"), because both describe how the evidence was collected rather
     than what was concluded. Say it once when they agree. */
  document.getElementById('ws-pin').textContent = (pin.label && pin.label!==tier) ? tier+' — '+pin.label : tier;
  document.getElementById('ws-status').textContent='Claim '+j.claim.status+'. A claim never changes the public pin; attested in-app capture does.';
  document.getElementById('ws-incentives').textContent=j.incentives||'';
  claimSessionSave(rec);
  showScreen('claim-workspace');
}
document.getElementById('btn-ws-capture').addEventListener('click',()=>{
  const rec=claimRecord || claimSessionLoad();
  if(!rec){ toast('No approved claim in this session'); return; }
  fetch(CLAIM_API+'/'+rec.claim_id+'/workspace?token='+encodeURIComponent(rec.token))
    .then(r=>r.json().then(j=>({ok:r.ok,j})))
    .then(({ok,j})=>{
      if(!ok || !j.pin){ toast('Workspace is not ready yet'); return; }
      scanTarget={id:j.pin.place_id, name:j.pin.name, lat:j.pin.location.lat, lng:j.pin.location.lng};
      startScan(true, {ownerAttest:true});
    })
    .catch(()=>toast("Couldn't start guided capture"));
});
document.getElementById('btn-ws-dispute').addEventListener('click', async ()=>{
  const rec=claimRecord || claimSessionLoad();
  const note=document.getElementById('ws-dispute').value.trim();
  if(!rec){ toast('No approved claim in this session'); return; }
  if(!note){ toast('Write what should change'); return; }
  try{
    const r=await fetch(CLAIM_API+'/'+rec.claim_id+'/dispute',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token:rec.token, note})
    });
    const j=await r.json().catch(()=>({}));
    if(!r.ok){ toast(j.detail || "Couldn't send the dispute"); return; }
    document.getElementById('ws-dispute').value='';
    toast("Thanks — we'll review your note. The public pin is unchanged.");
  }catch(e){ toast("Couldn't send the dispute"); }
});
function maybeOpenClaimFromHash(){
  if(location.hash==='#claim'){ closeSheets(); initClaimFind(); showScreen('claim-find'); }
}
claimRecord=claimSessionLoad();
maybeOpenClaimFromHash();
window.addEventListener('hashchange', maybeOpenClaimFromHash);
document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>{
  if(b.dataset.goto==='screen-profile') resetNav();
  showScreen(b.dataset.goto);
}));

