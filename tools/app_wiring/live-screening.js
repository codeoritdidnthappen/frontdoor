/* ===================== live camera + same-origin screening =====================
   Real rear-camera capture inside the phone frame, checked and published by the server that
   serves this page. Every URL is relative: one origin, no CORS. Contracts
   (frontdoor_server/screen_view.py and scan_view.py):
     POST /screen           assess only, retains nothing. Fired at the shutter so the review
                            screen shows real verdicts before anything is kept.
     POST /screen/publish   the consent step, fired by "Publish scan": the same blur → audit →
                            integrated assessment, and — only when the face audit answers
                            "clear" — the processed frame is stored and one scan record joins
                            the live map. multipart/form-data: 1-6 image parts; place_id, or
                            lat + lng + name; optional X-Frontdoor-Contributor header.
                            200 {published:true, scan_id, image_keys, faces_blurred,
                            assessment:{criteria}} · 200 {published:false, quarantined:true,
                            quarantine_reason:"face_check"} (nothing stored) · 503 {publish_reason,
                            publish_detail, assessment} when assessed but not stored.
     GET  /scan/photo/<key> the stored, privacy-processed photo for the card.
   The simulated pipeline runs only where there is no server to talk to at all — this page
   opened from a file:// URL — and the review says so. A real request that fails, times out or
   answers badly is reported as a scan that could not be completed, with a retry; it never
   becomes verdicts, never takes the Scanned tier, and never enters the scanned count.
   A server error is shown, never hidden.
   Privacy: the captured frame lives in these variables only — never localStorage. */
const SCREEN_API = '/screen';
const PUBLISH_API = '/screen/publish';
const PHOTO_API = '/scan/photo/';
const CLAIM_API = '/claim';
const camVideo = document.getElementById('cam-video');
let camStream = null;    /* active MediaStream while the viewfinder is live */
let liveFrame = null;    /* {blob, dataUrl} of the captured frame — in-memory only */
let liveUpload = null;   /* pending fetch promise */
let liveSettled = true;  /* false while the POST is in flight */
let liveResult = null;   /* parsed /screen JSON, or null → simulated verdicts */
let liveAbort = null;
let liveError = null;    /* the server's error detail when /screen answered but could not assess */
let liveNetFail = false; /* the POST failed outright: offline, aborted, or timed out */
let liveTimedOut = false;/* the 30s client abort fired — the same 30s gunicorn allows the model */
let liveRun = 0;         /* generation: a reset must not be overwritten by the POST it aborted */
let scanFromCard = false;/* startScan(true) from a card: publish against that place_id */
let ownerAttest = false; /* workspace guided capture: attested in-app only */
let fromLibrary = false; /* camera-roll path cannot attest */
let geoFix = null;       /* {lat,lng} from the phone while scanning; cleared on exit */
/* There is a server whenever this page came from one. A request to it that fails is a failed
   scan, not an absent server: only a file:// open — where no relative POST can ever go
   anywhere — may fall back to the staged pipeline. */
const HAS_SERVER = location.protocol.startsWith('http');
const liveSimulated = ()=> !HAS_SERVER || !liveFrame;
/* why a real scan produced no verdicts. Always a failure; never a substitute for one. */
function liveFailure(){
  if(liveError) return 'the server could not check this photo — '+String(liveError).replace(/\.$/,'');
  if(liveTimedOut) return 'the scan timed out after 30 seconds';
  if(liveNetFail) return 'this phone could not reach the server';
  return 'the scan did not finish';
}

function stopCamera(){
  if(camStream){camStream.getTracks().forEach(t=>t.stop());camStream=null;}
  camVideo.srcObject=null; camVideo.hidden=true;
  document.getElementById('viewfinder').classList.remove('live');
}
function resetLive(){
  liveRun++;                                  /* the aborted POST's handlers become no-ops */
  if(liveAbort){liveAbort.abort();liveAbort=null;}
  liveFrame=null; liveUpload=null; liveResult=null; liveSettled=true;
  liveError=null; liveNetFail=false; liveTimedOut=false;
}
async function tryStartCamera(){
  if(!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) return false;
  try{
    camStream = await navigator.mediaDevices.getUserMedia({
      video:{facingMode:{ideal:'environment'}, width:{ideal:1280}, height:{ideal:1706}},
      audio:false
    });
    /* only attach if the capture screen is still up (user may have cancelled mid-prompt) */
    if(!document.getElementById('scan-capture').classList.contains('active')){stopCamera();return false;}
    camVideo.srcObject=camStream; camVideo.hidden=false;
    document.getElementById('viewfinder').classList.add('live');
    return true;
  }catch(e){ stopCamera(); return false; } /* denied / unavailable → staged capture */
}
function captureFrame(){
  const w=camVideo.videoWidth, h=camVideo.videoHeight;
  if(!w||!h) return Promise.resolve(null);
  const scale=Math.min(1, 1280/Math.max(w,h));
  const c=document.createElement('canvas');
  c.width=Math.round(w*scale); c.height=Math.round(h*scale);
  c.getContext('2d').drawImage(camVideo,0,0,c.width,c.height);
  const dataUrl=c.toDataURL('image/jpeg',.85);
  return new Promise(res=>c.toBlob(b=>res(b?{blob:b,dataUrl}:null),'image/jpeg',.85));
}
function errorText(j, status){ return (j && (j.detail || j.error)) || ('HTTP '+status); }
function startLiveUpload(frame){
  liveRun++;                                  /* a second shutter supersedes the first */
  if(liveAbort) liveAbort.abort();
  liveResult=null; liveError=null; liveNetFail=false; liveTimedOut=false; liveSettled=false;
  liveAbort = ('AbortController' in window) ? new AbortController() : null;
  const run=liveRun, mine=()=>run===liveRun;
  const fd=new FormData();
  fd.append('images', frame.blob, 'scan.jpg');
  /* no entrance_id: map places are place ids, not frontdoor entrance ids — an invalid id would 400 */
  const ctl=liveAbort;
  const timer=setTimeout(()=>{if(!mine())return; liveTimedOut=true; if(ctl)ctl.abort();},30000);
  /* the two outcomes are kept apart on purpose: the rejection handler is the TRANSPORT
     failing, and a throw inside the fulfilled handler falls to the .catch below as a
     server-side failure. Neither one is evidence that no server exists, so neither
     selects the staged pipeline — both land on the review screen as a failed scan. */
  liveUpload = fetch(SCREEN_API,{method:'POST',body:fd,signal:liveAbort?liveAbort.signal:undefined})
    .then(r=>r.json().catch(()=>({})).then(j=>{
      if(!mine()) return;
      if(r.ok && j.assessment && j.assessment.criteria) liveResult=j;
      else liveError=errorText(j, r.status);          /* answered but could not assess: shown on review */
    }), ()=>{ if(mine()) liveNetFail=true; })          /* offline, aborted, or timed out */
    .catch(()=>{ if(mine() && !liveError) liveError='the answer could not be read'; })
    .then(()=>{ clearTimeout(timer); if(mine()) liveSettled=true; });
}

/* ---- where a scan publishes: the card it was launched from, or the phone's fix + a typed name ---- */
function requestGeoFix(){
  geoFix=null;
  if(scanFromCard || !navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    pos=>{ geoFix={lat:pos.coords.latitude, lng:pos.coords.longitude}; },
    ()=>{ geoFix=null; },
    {enableHighAccuracy:true, timeout:8000, maximumAge:60000});
}
function nearestPlaces(origin, n){
  return [...places].sort((a,b)=>Math.hypot(a.lat-origin.lat,a.lng-origin.lng)-Math.hypot(b.lat-origin.lat,b.lng-origin.lng)).slice(0,n);
}
function renderEntranceField(){
  const input=document.getElementById('entrance-name');
  const origin = geoFix || (scanFromCard ? scanTarget : LOC);
  document.getElementById('entrance-options').innerHTML =
    nearestPlaces(origin, 8).map(p=>`<option value="${esc(p.name).replace(/"/g,'&quot;')}"></option>`).join('');
  if(scanFromCard && !input.value) input.value=scanTarget.name;
  document.getElementById('entrance-hint').textContent = scanFromCard
    ? 'Started from this entrance — change the name if it is a different door.'
    : geoFix ? 'Suggestions are the businesses nearest your location.'
    : 'Location is off — pick a business from the suggestions.';
}
/* {place_id?, name, lat, lng, place?} for /screen/publish, or null when nothing can be sent */
function resolvePlaceRef(){
  const text=document.getElementById('entrance-name').value.trim();
  if(!text) return null;
  const match = (scanFromCard && scanTarget.name===text) ? scanTarget : places.find(p=>p.name===text);
  if(match) return {place_id:match.id, name:match.name, lat:match.lat, lng:match.lng, place:match};
  const at = geoFix || (scanFromCard ? scanTarget : null);
  if(!at) return null;
  return {name:text, lat:at.lat, lng:at.lng, place:null};
}
/* anonymous contributor token: random, made once, the only thing this app keeps in localStorage */
let sessionToken=null;
function contributorToken(){
  const KEY='entrymap.contributor';
  const fresh=()=>{ const b=new Uint8Array(16); crypto.getRandomValues(b); return 'em_'+Array.from(b,x=>x.toString(16).padStart(2,'0')).join(''); };
  try{
    let t=localStorage.getItem(KEY);
    if(!/^[A-Za-z0-9._-]{8,64}$/.test(t||'')){ t=fresh(); localStorage.setItem(KEY,t); }
    return t;
  }catch(e){ return sessionToken || (sessionToken=fresh()); }
}

