function critFromAssessment(a){
  const crit={};
  LIVE_CRITERIA.forEach(key=>{
    const c=a.criteria[key]; if(!c) return;
    crit[LIVE_TO_DOOR[key]]={v:c.verdict, c:+c.confidence||0, e:String(c.evidence||'')};
  });
  return crit;
}
/* POST /screen/publish → {kind: published | quarantined | held | error | net, body?, detail?} */
async function publishScan(ref){
  const fd=new FormData();
  fd.append('images', liveFrame.blob, 'scan.jpg');
  if(ref.place_id) fd.append('place_id', ref.place_id);
  fd.append('name', ref.name); fd.append('lat', String(ref.lat)); fd.append('lng', String(ref.lng));
  fd.append('capture_kind', fromLibrary ? 'camera_roll' : 'in_app');
  if(ownerAttest){
    /* the server proves the attestation against THIS claim's token, not against the
       existence of somebody's claim, so the guided capture carries the credential */
    const rec=claimRecord || claimSessionLoad();
    if(!rec) return {kind:'error', detail:'the approved claim for this door is not in this session — reopen the workspace'};
    fd.append('attested', '1');
    fd.append('claim_id', rec.claim_id);
    fd.append('token', rec.token);
  }
  const ctl=('AbortController' in window) ? new AbortController() : null;
  const timer=setTimeout(()=>{if(ctl)ctl.abort();},45000);
  let r, j;
  try{
    r=await fetch(PUBLISH_API,{method:'POST',body:fd,headers:{'X-Frontdoor-Contributor':contributorToken()},signal:ctl?ctl.signal:undefined});
    j=await r.json().catch(()=>({}));
  }catch(e){ clearTimeout(timer); return {kind:'net'}; }
  clearTimeout(timer);
  const assessed = !!(j && j.assessment && j.assessment.criteria);
  if(r.ok && j.published) return {kind:'published', body:j};
  if(r.ok && assessed && j.quarantined) return {kind:'quarantined', body:j};
  if(r.status===503 && assessed) return {kind:'held', body:j, detail:j.publish_detail||j.detail||'storage was unavailable'};
  return {kind:'error', detail:errorText(j, r.status)};
}
function placeForRef(ref, id){
  if(ref.place) return ref.place;
  const p={id, name:ref.name, lat:ref.lat, lng:ref.lng, crit:{}, tier:'est'};
  places.push(p);
  return p;
}
/* Only a run the server actually read gets here: it is what moves a pin to Scanned on-site,
   and therefore what the "N of M entrances scanned" count is counting. A simulated run never
   calls this — see the publish handler. */
function upgradePin(p, crit, publish, photo, note){
  if(p.tier!=='owner') p.tier='scan';
  p.views=(p.views|0)+1; p.staged=true; p.date=new Date().toISOString().slice(0,10);
  p.crit=crit; p.publish=publish; p.livePhoto=photo; p.note=note;
  p.f=featsOf(p);
}
document.getElementById('btn-publish').addEventListener('click',async ()=>{
  const btn=document.getElementById('btn-publish');
  const ref=resolvePlaceRef();
  if(!ref){
    toast(document.getElementById('entrance-name').value.trim() ? 'Pick a business from the suggestions — location is off' : 'Name the entrance first');
    document.getElementById('entrance-name').focus();
    return;
  }
  let p, simulated=liveSimulated();
  if(simulated){
    /* No frame, or no server at all. Nothing read a photograph, so nothing is published and
       nothing is written anywhere: an entrance already on the map is shown exactly as it was,
       and one that is not on the map stays off it. The done screen is told the outcome
       directly, so it never has to read it back off a pin this run did not touch. */
    p=ref.place || {id:null, name:ref.name, lat:ref.lat, lng:ref.lng, tier:'est'};
  } else {
    btn.disabled=true; btn.textContent='Publishing…';
    let out;
    try{ out=await publishScan(ref); } finally{ btn.disabled=false; btn.textContent='Publish scan'; }
    if(out.kind==='error'){ toast("Couldn't publish — "+out.detail); return; }   /* stays on review to retry or retake */
    if(out.kind==='net'){
      if(!liveResult){ toast('Lost the server before publishing — try again'); return; }
      out={kind:'held', body:liveResult, detail:'the server could not be reached to publish.'};
    }
    const b=out.body, crit=critFromAssessment(b.assessment);
    p=placeForRef(ref, out.kind==='published' ? 'scan:'+b.scan_id : 'scan:held-'+Date.now());
    if(out.kind==='published'){
      /* the stored, privacy-processed photo is the card's photo, streamed back from the server */
      upgradePin(p, crit, {state:'published', scanId:b.scan_id, faces:b.faces_blurred|0},
        (b.image_keys && b.image_keys.length) ? PHOTO_API+b.image_keys[0] : null,
        'Published to the live map just now, checked by the model. '+(b.wording||''));
    } else if(out.kind==='quarantined'){
      /* privacy hold: the server stored nothing; the verdicts stay on this phone, the photo is withheld */
      upgradePin(p, crit, {state:'quarantined'}, null,
        'Privacy hold: the face check could not confirm every face is blurred, so nothing was stored or published. These verdicts are only on this phone.');
    } else {
      /* assessed but not published (storage down, or no route): the verdicts stand, kept here, not on the live map */
      upgradePin(p, crit, {state:'held', detail:out.detail}, liveFrame.dataUrl,
        'Checked by the model, but not published: '+out.detail+' Saved for later on this phone — it is not on the live map yet.');
    }
  }
  scanTarget=p;
  showScreen('scan-done');
  runDone(p, simulated);
});
function doneHeading(p, simulated){
  if(simulated) return 'Simulated scan — nothing was published';
  const s=p.publish&&p.publish.state;
  return s==='published' ? 'Scan published — thanks for helping your neighbors'
    : s==='quarantined' ? 'Privacy hold — the photo stays off the map'
    : 'Scan saved for later — not published yet';
}
/* ROUND 11's provenance row, sized to this page rather than to the design source.
   The design has one outcome and says, flatly, that the scan was added to the
   entrance's receipt. This page has four, and the same rule as doneHeading() above
   applies: a screen may only claim what the server actually did. Only a published
   run joins a receipt, so only a published run says so.
   Told the outcome, exactly like doneHeading: `simulated` is answered before the pin
   is looked at, so a simulated run against an entrance somebody really published
   earlier cannot read that earlier publish back as this run's result. */
function doneProvenance(p, simulated){
  if(simulated) return {main:'Simulated scan',
    sub:"Nothing was published, so nothing joined this entrance's receipt."};
  const s=p.publish&&p.publish.state;
  return {main:'Your scan', sub:
    s==='published' ? "Added to this entrance's receipt as a dated source — sources, dates, and confidence, not a badge."
    : s==='quarantined' ? "On privacy hold — the photo was not stored, and nothing has joined this entrance's receipt."
    : "Assessed, but not published yet — it joins this entrance's receipt when it reaches the map."};
}
function runDone(p, simulated){
  const h=document.querySelector('#scan-done .scan-h');
  if(h) h.textContent=doneHeading(p, simulated);
  const scans = places.filter(q=>q.tier!=='est').length;
  document.getElementById('counter-line').textContent = simulated
    ? `${esc(p.name)} is unchanged — a simulated run publishes nothing · ${scans} of ${places.length} entrances scanned downtown`
    : `${esc(p.name)} just moved up a tier · ${scans} of ${places.length} entrances scanned downtown`;
  document.getElementById('done-legend').innerHTML =
    `<span class="lg">${pinSVG('est',pinPx('est','receipt'))} Estimated</span>
     <span class="lg">${pinSVG('scan',pinPx('scan','receipt'))} Scanned on-site</span>
     <span class="lg">${pinSVG('owner',pinPx('owner','receipt'))} Owner-confirmed</span>`;
  /* mini-map centered on the new pin */
  const mm=document.getElementById('mini-map');
  const W=mm.clientWidth||320,Hh=210;
  mm.innerHTML=groundSVG(W,Hh,16,BBOX);
  const near=places.filter(q=>Math.abs(q.lat-p.lat)<0.0012&&Math.abs(q.lng-p.lng)<0.0016&&q!==p).slice(0,8);
  const box={lat0:p.lat-0.0009,lat1:p.lat+0.0009,lng0:p.lng-0.0013,lng1:p.lng+0.0013};
  const pr=(la,ln)=>[ (ln-box.lng0)/(box.lng1-box.lng0)*W, (1-(la-box.lat0)/(box.lat1-box.lat0))*Hh ];
  near.forEach(q=>{
    const [x,y]=pr(q.lat,q.lng);
    if(x<10||x>W-10||y<10||y>Hh-10)return;
    const d=document.createElement('div');
    d.className='minipin';
    d.style.cssText=`position:absolute;left:${x}px;top:${y}px;pointer-events:none;--mh:${q.tier==='est'?20:26}px`;
    d.innerHTML=`<span class="pin">${pinSVG(q.tier,pinPx(q.tier,'receipt'))}</span>`;
    mm.appendChild(d);
  });
  /* ROUND 11: the provenance row, in the receipt's own words and its own component --
     the first thing a contributor is shown about their scan is the shape it takes on
     somebody else's card: a dated source, never a badge. It falls inside the region
     this op replaces, so it only reaches the served page through here. What it says
     is doneProvenance()'s decision, above, for the same reason the heading is
     doneHeading()'s: this screen renders the outcome it was handed. */
  const day=fmtDay(APP_TODAY.join('-'));
  const prov=doneProvenance(p, simulated);
  document.getElementById('done-prov').innerHTML = provRow(
    iconSVG('camera',17,'var(--marigold-ink,#6B4014)'),
    `<b>${prov.main} · ${day}</b>`,
    `<span class="pr-sub">${prov.sub}</span>`,
    'done-scan');
  const dp=document.querySelector('#done-prov .prov-row');
  if(dp){
    /* a run that reached no card -- a simulated scan of an entrance that is not on the
       map -- has no receipt to open, so the row states the outcome and opens nothing */
    const opens = !!p.id;
    dp.setAttribute('aria-label', `${prov.main}, ${day} — ${prov.sub}`+(opens?' Opens the receipt.':''));
    if(opens) dp.addEventListener('click',()=>{ showScreen('screen-map'); openCard(p.id,'full'); });
    else { dp.disabled=true; dp.setAttribute('aria-disabled','true'); }
  }
  const d=document.createElement('div');
  d.style.cssText=`position:absolute;left:${W/2}px;top:${Hh/2}px;pointer-events:none;--mh:34px`;
  d.className='minipin'+(simulated?'':' pin-drop');
  /* spec: "Live scan drop: 64 px Scanned on-site pin." The tier is the pin's own, so a
     simulated run — which upgrades nothing — cannot draw itself a Scanned pin. */
  d.innerHTML=`<span class="pin">${pinSVG(p.tier,64)}</span>${(simulated||isReduced())?'':'<span class="rippler"></span>'}`;
  mm.appendChild(d);
}
document.getElementById('btn-done-map').addEventListener('click',()=>{
  showScreen('screen-map');
  setZoom(false, null);   /* ROUND 9: zoom AND centre back to the pilot frame.
                             setZoom took a second argument this round; carried from
                             the design source, which owns this line. */
  renderNearby();
  /* bounce the upgraded pin on the real map too */
  const b=pinsEl.querySelector(`[data-id="${scanTarget.id}"]`);
  if(b&&!isReduced()){b.classList.add('pin-drop');const r=document.createElement('span');r.className='rippler';b.appendChild(r);setTimeout(()=>{b.classList.remove('pin-drop');r.remove();},2200);}
  /* a simulated run against an entrance that is not on the map has no card to open */
  if(places.some(q=>q.id===scanTarget.id)) after(isReduced()?0:600,()=>openCard(scanTarget.id,'medium'));
});

