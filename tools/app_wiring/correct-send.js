/* "Send suggestion" posts to POST /correct, and a failure says so.

   The design source's handler pushed the note into a local array and went straight to the
   "Correction submitted" screen — a success screen for something that had not been sent.
   This is the same honesty rule the scan path got when it used to show fabricated verdicts:
   the confirmation screen is only ever reached by a request the server answered 201, and
   every other outcome stays on the sheet, says what happened, and lets the person retry.

   multipart/form-data: place_id (or lat + lng + name), category, scope, note, and an
   optional single photo — privacy-processed on the server before anything persists.
   No entrance_id: map places are place ids, not frontdoor entrance ids (the server refuses
   a sealed one either way). The contributor token is the same header the scan path sends. */
function correctionCategory(){
  return ['entrance_features','business_identity','photo_issue','other'][document.getElementById('correct-what').selectedIndex] || 'other';
}
function correctionScope(){
  return document.getElementById('correct-which').selectedIndex===1 ? 'other_entrance' : 'this_entrance';
}
async function postCorrection(note, file){
  const fd=new FormData();
  const p=correctTarget;
  if(p && p.id) fd.append('place_id', String(p.id));
  if(p && p.name) fd.append('name', p.name);
  if(p && typeof p.lat==='number'){ fd.append('lat', String(p.lat)); fd.append('lng', String(p.lng)); }
  fd.append('category', correctionCategory());
  fd.append('scope', correctionScope());
  fd.append('note', note);
  if(file) fd.append('photo', file, file.name||'correction.jpg');
  const ctl=('AbortController' in window) ? new AbortController() : null;
  const timer=setTimeout(()=>{if(ctl)ctl.abort();},45000);
  let r, j;
  try{
    r=await fetch(CORRECT_API,{method:'POST',body:fd,
      headers:{'X-Frontdoor-Contributor':contributorToken()},
      signal:ctl?ctl.signal:undefined});
    j=await r.json().catch(()=>({}));
  }catch(e){ clearTimeout(timer); return {ok:false, detail:'this phone could not reach the server'}; }
  clearTimeout(timer);
  if(r.ok && j && j.received) return {ok:true, body:j};
  return {ok:false, detail:errorText(j, r.status)};
}
document.getElementById('btn-correct-send').addEventListener('click',async ()=>{
  const btn=document.getElementById('btn-correct-send');
  const note=cNote.value.trim();
  const cpf=document.getElementById('correct-photo');
  const file=(cpf && cpf.files && cpf.files[0]) || null;
  if(!note && !file){
    setCorrectError(true);
    cNote.focus();
    announceUI('Correction not sent. Tell us what you noticed, or add a photo.');
    return;
  }
  setCorrectError(false);
  if(!HAS_SERVER){
    /* opened from a file:// URL: no relative POST can go anywhere. Saying "sent" here is
       exactly the defect this ticket is about, so it says the opposite. */
    toast('Opened without a server — a correction cannot be sent from here');
    announceUI('Correction not sent. This page was opened without a server.');
    return;
  }
  btn.disabled=true; btn.textContent='Sending…';
  let out;
  try{ out=await postCorrection(note, file); }
  finally{ btn.disabled=false; btn.textContent='Send suggestion'; }
  if(!out.ok){
    toast("Couldn't send — "+out.detail);
    announceUI('Correction not sent. '+out.detail+'. Your note is still here — try again.');
    return;   /* the sheet stays open with the note and photo intact, so nothing is lost */
  }
  corrDoneTarget = correctTarget;
  document.getElementById('corr-done-biz').innerHTML =
    `<span class="cr-icon">${iconSVG('store',20,'var(--purple-ink)')}</span>
     <div><div class="cr-name">${esc(correctTarget?correctTarget.name:'This entrance')}</div>
     <span class="cr-sub">${esc(correctTarget?(correctTarget.addr||entranceSub(correctTarget)):'')}</span>
     ${note?`<span class="cr-sub" style="color:var(--ink);font-style:italic;margin-top:var(--sp-2)">“${esc(note)}”</span>`:''}</div>`;
  cNote.value=''; setCorrectError(false); document.getElementById('correct-count').textContent='0';
  if(cpf) cpf.value='';
  const cpl=document.getElementById('correct-photo-label'); if(cpl) cpl.textContent='Choose a photo';
  loadMyCorrections();      /* the tab shows what the server holds, including this one */
  closeSheets();
  goScreen('screen-corr-done');
});
