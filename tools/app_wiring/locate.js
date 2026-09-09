/* ===================== the locate control, and where you actually are =====================
   THE DEFECT THIS REPLACES. The design source's handler was one line, and it asked
   the phone nothing: it reset the pan, returned the frame to the pilot bbox, and
   raised a toast asserting the map was now centred on you, naming 2nd & Colorado --
   to a person who may be a thousand miles from it. A control that does not work and
   a false statement in the same line. (The line itself is in WIRING_FORBIDDEN in
   tools/port_app_page.py, quoted there once so it can never come back, which is why
   it is described here rather than reproduced.)

   navigator.geolocation is the only thing that knows, so the control asks it, and
   every answer it can give is reported as itself:

     not asked yet   the browser's own prompt is the interaction; we add no dialog in
                     front of it, and we never ask on load
     granted         the map centres on the real fix and the mark is drawn there
     denied          said once, in the product's voice, the map does not move, and
                     tapping again re-explains rather than re-prompting -- a denied
                     permission is an answer
     unavailable     said as ITS OWN thing, separately from a timeout and separately
     / timed out     from denied, because a person acts on each differently
     outside the     the map covers a few blocks of downtown Austin. A fix elsewhere
     pilot area      gets the empty-area invite, saying we have mapped nothing there
                     yet -- never a verdict about the places around them

   The rule the toast copy is written against: nothing here says "Centered on you"
   unless the map is centred on a real fix.

   WHY THIS IS WIRING RATHER THAN DESIGN. Geolocation is a permission the browser
   grants to this origin, its failures are conditions this repository has to report
   honestly, and the same false line is still in the prototype this design source is
   refreshed from. As an op, a refresh either carries the honest handler or fails the
   port loudly; as a hand edit to the design source it would come back silently. */

/* idle | asking | ok | denied | unavailable -- `var`, because renderMap() is defined
   above this fragment and may run before these lines do; a hoisted `undefined` reads
   as "no fix" everywhere below, where a TDZ `let` would throw. */
var geoState = 'idle';
var youFix = null;      /* the last real fix, {lat,lng}, or null */
var youAway = '';       /* how far that fix is from the pilot area, in words */
var youOutside = false; /* a real fix, far enough out that the map has nothing to show */

/* The pilot bbox is about 600m by 580m. A fix within GEO_NEAR_KM of its centre is
   close enough that the mapped blocks are still the useful answer; past that, the
   nearest pin is not "near" in any sense a person walking would recognise. */
const GEO_NEAR_KM = 1.5;
const GEO_OPTS = {enableHighAccuracy:true, timeout:10000, maximumAge:60000};

function pilotCentre(){ return {lat:(BBOX.lat0+BBOX.lat1)/2, lng:(BBOX.lng0+BBOX.lng1)/2}; }
function inPilot(f){
  return !!f && f.lat>=BBOX.lat0 && f.lat<=BBOX.lat1 && f.lng>=BBOX.lng0 && f.lng<=BBOX.lng1;
}
/* great-circle km; the pins' Math.hypot on degrees is fine for ordering a few blocks
   and useless for "how far away is Chicago", which is the sentence this feeds */
function kmApart(a,b){
  const R=6371, rad=Math.PI/180;
  const dLat=(b.lat-a.lat)*rad, dLng=(b.lng-a.lng)*rad;
  const s=Math.sin(dLat/2)**2 + Math.cos(a.lat*rad)*Math.cos(b.lat*rad)*Math.sin(dLng/2)**2;
  return 2*R*Math.asin(Math.min(1,Math.sqrt(s)));
}
/* "a few hundred feet from" / "about 3 miles from" / "about 1,190 miles from" --
   a distance a person can picture, never a false precision */
function awayLabel(km){
  const mi = km*0.621371;
  if(mi < 0.2) return 'a few hundred feet from';
  const n = mi < 3 ? Math.round(mi*10)/10 : Math.round(mi);
  return 'about '+n.toLocaleString()+' '+(n===1?'mile':'miles')+' from';
}

/* ---- the control's own name and busy state ---------------------------------
   7.6: the name describes what the control does NOW. After a denial it no longer
   shows a location, so it no longer says it does. */
const locateBtn = document.getElementById('locate-btn');
const LOCATE_NAME = {
  idle:        'Show my location on the map',
  asking:      'Finding your location',
  ok:          'Show my location on the map',
  denied:      'Why your location is not shown',
  unavailable: 'Try again for your location'
};
function paintLocateBtn(){
  if(!locateBtn) return;
  locateBtn.setAttribute('aria-label', LOCATE_NAME[geoState] || LOCATE_NAME.idle);
  locateBtn.setAttribute('aria-busy', geoState==='asking' ? 'true' : 'false');
}
paintLocateBtn();

/* ---- an error is announced as an error --------------------------------------
   #sr-announce is role="status" and polite: right for "Centered on you", wrong for
   a control that could not do what it says. A denial or a failure goes to a
   role="alert" region as well, with the sentence that says what to do about it. The
   region is created here rather than in the markup so a design refresh cannot drop
   it, and it is added to INERT_EXEMPT for the same reason #sr-announce is: inert
   would silence it while a sheet is open. */
function geoAlert(msg){
  let el=document.getElementById('geo-alert');
  if(!el){
    el=document.createElement('div');
    el.id='geo-alert'; el.className='sr-only'; el.setAttribute('role','alert');
    const sr=document.getElementById('sr-announce');
    if(sr && sr.parentNode) sr.parentNode.insertBefore(el, sr.nextSibling);
    else document.body.appendChild(el);
    if(typeof INERT_EXEMPT!=='undefined') INERT_EXEMPT.add('geo-alert');
  }
  el.textContent=''; setTimeout(()=>{ el.textContent=msg; },30);
}
/* a fix that lands answers the failure that came before it, so the failure stops
   standing in the accessibility tree for anyone reading the page rather than hearing
   the announcement */
function clearGeoAlert(){
  const el=document.getElementById('geo-alert');
  if(el) el.textContent='';
}

/* ---- the "you are here" mark -------------------------------------------------
   One mark, reused: if a design round ships its own #you-here this adopts it rather
   than drawing a second one. It is drawn ONLY where the fix really is -- if the
   projected point is off the frame the mark is hidden rather than pinned to an edge,
   because a mark at the edge would say "you are there" about somewhere you are not.
   role="img" with a name, not a button: it is not a place and it opens nothing. */
function youHereEl(){
  let el=document.getElementById('you-here');
  if(!el){
    el=document.createElement('div');
    el.id='you-here';
    el.setAttribute('role','img');
    el.setAttribute('aria-label','You are here');
    el.hidden=true;
    (document.getElementById('map') || document.body).appendChild(el);
  }
  return el;
}
function placeYouHere(){
  const el=youHereEl();
  if(geoState!=='ok' || !youFix){ el.hidden=true; return; }
  const W=mapEl.clientWidth, H=mapEl.clientHeight;
  if(!(W>40) || !(H>40)){ el.hidden=true; return; }
  /* the same projection and the same 22px pad mapLayout gives every pin, so the mark
     and the pins are in one coordinate system at every zoom and centre */
  const xy=proj(youFix.lat, youFix.lng, W, H, 22);
  const on = xy[0]>=0 && xy[0]<=W && xy[1]>=0 && xy[1]<=H;
  el.hidden = !on;
  if(on){ el.style.left=xy[0]+'px'; el.style.top=xy[1]+'px'; }
}

/* ---- the empty-area invite, and which of its two causes is open --------------
   Called from renderMap (the map_empty_cause op). Zero pins after a filter and a fix
   outside the pilot area are different facts, so they get different words. Neither
   is ever a statement about the places themselves: "nothing is mapped here yet" is
   about us. */
function paintEmptyInvite(noPins){
  const me=document.getElementById('map-empty');
  if(!me) return;
  const out=!!youOutside;
  me.classList.toggle('on', !!noPins || out);
  const h=me.querySelector('.me-h'), p=me.querySelector('.me-p');
  const area=document.getElementById('me-area');
  if(out){
    if(h) h.textContent='EntryMap has not mapped your area yet';
    if(p) p.textContent='You are '+youAway+' the few blocks of downtown Austin this '
      +'pilot covers, so there is nothing here to show you. That is what we have '
      +'mapped — it says nothing about the places around you.';
    if(area) area.textContent='Show the mapped area';
  } else {
    if(h) h.textContent='No entrances mapped here yet';
    if(p) p.textContent='Be the first to help neighbors plan ahead.';
    if(area) area.textContent='Try another area';
  }
}

/* ===================== one question, asked once, for every control that asks ==========
   Two controls in this app ask the browser where the phone is: the map's locate
   button, and onboarding's "Allow location" (tools/app_wiring/onboarding-location.js).
   A third, the Location switch in Settings, is the standing claim about the answer.

   There are eight things the browser can say, and every one of them has to be told
   apart from the others: not asked yet, granted inside the pilot area, granted near
   it, granted far from it, denied, position unavailable, timed out, no geolocation
   API at all, and a page the browser will not answer for because it is not secure.

   The branching that decides which one happened lives HERE, once. Two copies of it is
   how one copy drifts back into staging the appearance of an outcome instead of
   producing it -- the defect this file exists to remove, found a second time on the
   onboarding step (#488). What each control DOES with the answer is its own: a map
   moves or does not move, an onboarding step sets a switch and carries on. Those are
   presentation and they differ honestly. The answer itself does not differ, so it is
   not computed twice. */

/* What can be known before the browser is asked. Both are checked BEFORE
   getCurrentPosition, because a browser answers "denied" for an insecure page, and
   being told a permission was refused when it was never offered is the wrong thing to
   act on. A remembered denial is checked here too: a denied permission is an answer,
   and asking again on the next tap is not listening to it. */
function geoPrecheck(){
  if(!navigator.geolocation) return {kind:'no-api'};
  if(!window.isSecureContext || location.protocol==='file:') return {kind:'insecure'};
  if(geoState==='denied') return {kind:'denied', remembered:true};
  return null;
}
/* A granted fix is one answer with three shapes, because "we know where you are" and
   "we have mapped anything near you" are different facts. */
function geoFixOutcome(pos){
  const fix={lat:pos.coords.latitude, lng:pos.coords.longitude};
  const km=kmApart(fix, pilotCentre());
  return {kind:'granted', fix:fix, km:km, away:awayLabel(km),
          where: inPilot(fix) ? 'inside' : (km<=GEO_NEAR_KM ? 'near' : 'far')};
}
/* Denied, timed out and unavailable are three different answers, because a person
   acts on each of them differently. */
function geoFailOutcome(err){
  const code = err && err.code;
  if(code===1) return {kind:'denied'};        /* PERMISSION_DENIED */
  if(code===3) return {kind:'timeout'};       /* TIMEOUT */
  return {kind:'unavailable'};                /* POSITION_UNAVAILABLE */
}

/* Recording the answer is separate from saying it, and it happens for every caller
   before any of them speaks. So a denial heard on the onboarding step is already the
   map control's name and the Settings switch's state by the time the map is reached,
   and a fix granted there is already the mark the map draws. One answer, one record. */
function recordGeoOutcome(o){
  if(o.kind==='granted'){
    geoState='ok'; geoPermission='granted';
    youFix=o.fix; youAway=o.away; youOutside = o.where==='far';
  } else {
    if(o.kind==='denied'){ geoState='denied'; geoPermission='denied'; }
    else if(o.kind==='no-api' || o.kind==='insecure'){ geoState='unavailable'; geoPermission=o.kind; }
    else { geoState='unavailable'; }   /* a timeout or an unavailable position says
                                          nothing about the permission, so neither
                                          does the switch */
    youFix=null; youAway=''; youOutside=false;
  }
  paintLocateBtn();
  paintLocToggle();
}

/* The one place navigator.geolocation is called. `say` is handed exactly one outcome,
   exactly once, after it has been recorded. Returns 'busy' if a request is already in
   flight (say is not called), 'answered' if the answer was known without asking (say
   has already run, synchronously), or 'asking' if the browser was really asked. */
function askGeo(say){
  if(geoState==='asking') return 'busy';       /* one request at a time */
  const pre=geoPrecheck();
  if(pre){ recordGeoOutcome(pre); say(pre); return 'answered'; }
  geoState='asking'; paintLocateBtn();
  navigator.geolocation.getCurrentPosition(
    pos=>{ const o=geoFixOutcome(pos); recordGeoOutcome(o); say(o); },
    err=>{ const o=geoFailOutcome(err); recordGeoOutcome(o); say(o); },
    GEO_OPTS);
  return 'asking';
}

/* ---- the map's words for the five answers that are not a fix ------------------ */
const GEO_STOPPED = {
  denied: {short:'Location is off for this site',
    why:'Location is off for this site, so the map has not moved and shows the pilot area '
      +'in downtown Austin. You can turn location back on for this site in your browser '
      +'settings.'},
  timeout: {short:'Finding your location timed out',
    why:'Finding your location took too long, so the map has not moved. '
      +'Tap the location button to try again.'},
  unavailable: {short:'Your location is not available',
    why:'Your device could not work out where it is, so the map has not moved. '
      +'Trying again, or outdoors, often works.'},
  'no-api': {short:'This browser cannot share a location',
    why:'This browser cannot share a location, so the map has not moved and shows the '
      +'pilot area in downtown Austin.'},
  insecure: {short:'Location needs a secure connection',
    why:'This page is not on a secure connection, so the browser will not share a '
      +'location. The map has not moved.'}
};

/* ---- the Settings switch, which is the standing claim ------------------------
   #loc-toggle ships as `class="toggle on" aria-checked="true"` and its handler flipped
   it on tap and toasted "Location on while using" -- so the app said location was on,
   visually and to a screen reader, on a first load where nothing had been asked. It is
   the same defect as #488's, on the same element.

   The switch is a claim about a permission, so its state is a function of the
   permission and of nothing else: it reads on only where the browser has actually said
   granted, and it is repainted from the real state as soon as this file runs, which is
   what takes the markup's opening claim down.

   Turning it off is not ours to do -- a page cannot revoke a permission the browser has
   granted -- so the control says where that is done rather than pretending to do it. */
var geoPermission = 'unknown';   /* unknown | prompt | granted | denied | no-api | insecure */
const locToggle = document.getElementById('loc-toggle');
const LOC_TOGGLE_SUB = {
  unknown:  'While using · not asked yet',
  prompt:   'While using · not asked yet',
  granted:  'On for this site · while using',
  denied:   'Off for this site · turn it on in browser settings',
  'no-api': 'This browser cannot share a location',
  insecure: 'Location needs a secure connection'
};
function paintLocToggle(){
  if(!locToggle) return;
  const on = geoPermission==='granted';
  locToggle.classList.toggle('on', on);
  locToggle.setAttribute('aria-checked', on ? 'true' : 'false');
  const row=locToggle.closest ? locToggle.closest('.prof-row') : null;
  const sub=row ? row.querySelector('.rowsub') : null;
  if(sub) sub.textContent = LOC_TOGGLE_SUB[geoPermission] || LOC_TOGGLE_SUB.unknown;
}
function locToggleSays(o){
  if(o.kind==='granted'){ clearGeoAlert(); toast('Location is on for this site'); return; }
  const said=GEO_STOPPED[o.kind];
  geoStopped(said.short, said.why);
}
if(locToggle){
  paintLocToggle();
  locToggle.addEventListener('click',()=>{
    if(geoPermission==='granted'){
      toast('Location is on in your browser for this site');
      geoAlert('This site has permission to use your location. A page cannot take that '
        +'back — you turn it off for this site in your browser settings.');
      return;
    }
    if(askGeo(locToggleSays)==='asking') toast('Finding your location…');
  });
}

/* ---- the map's half of the answer --------------------------------------------
   Every way of not getting a fix ends in geoStopped, and it clears what the LAST
   attempt left on the map. Without that, the mark from an earlier fix stays drawn --
   "You are here" over a point nothing has confirmed -- beside a control that has just
   said we do not know where you are, and the out-of-area invite keeps quoting a
   distance from a fix we no longer have. The re-render takes both down; a filter that
   legitimately empties the map keeps its own invite, because paintEmptyInvite still
   asks about the pins. */
function geoStopped(short, why){
  toast(short);
  geoAlert(why);
  youOutside=false;
  renderMap();
}
/* The rule the copy below is written against: nothing says "Centered on you" unless
   the map is centred on a real fix. */
function mapSaysGeo(o){
  if(o.kind==='granted'){
    clearGeoAlert();
    if(o.where==='inside'){
      panMap(0);
      setZoom(false, youFix);        /* re-renders, which draws the mark on the fix */
      toast('Centered on you — you are marked on the map');
    } else if(o.where==='near'){
      /* just outside: the frame moves as close to the fix as the pilot bbox allows,
         and the toast says that rather than claiming a centre it does not have */
      panMap(0);
      setZoom(false, youFix);        /* clamped to the pilot bbox by clampCentre */
      toast('You are just outside the mapped blocks — showing the nearest of them');
    } else {
      /* far out: the map does not move, because there is nothing of ours to move it to */
      renderMap();
      toast('EntryMap has not mapped your area yet');
    }
    return;
  }
  const said=GEO_STOPPED[o.kind];
  geoStopped(said.short, said.why);
}

function locateMe(){
  closeSheets();
  if(askGeo(mapSaysGeo)==='asking') toast('Finding your location…');
}
document.getElementById('locate-btn').addEventListener('click', locateMe);

/* If the browser will tell us the standing permission without prompting, every control
   is correct before any of them is pressed -- the map button is named for what it does
   now, and the Settings switch reads on only if the permission really is granted. A
   user who turns location back on in site settings gets controls that ask again instead
   of ones that keep repeating the refusal. Reading this state prompts nobody and
   fetches no position. */
if(navigator.permissions && navigator.permissions.query){
  navigator.permissions.query({name:'geolocation'}).then(st=>{
    const sync=()=>{
      if(st.state==='denied'){ geoState='denied'; geoPermission='denied'; youOutside=false; youFix=null; }
      else if(st.state==='granted'){ geoPermission='granted'; if(geoState==='denied') geoState='idle'; }
      else { geoPermission='prompt'; if(geoState==='denied') geoState='idle'; }
      paintLocateBtn(); paintLocToggle(); renderMap();
    };
    sync();
    st.onchange=sync;
  }).catch(()=>{});
}

/* ===================== empty-area invite ===================== */
document.getElementById('me-pin').innerHTML=illusSVG('street',236);
document.getElementById('me-scan').addEventListener('click',()=>{closeSheets();startScan();});
document.getElementById('me-area').addEventListener('click',()=>{
  /* the button has two jobs because the invite has two causes. Opened because a fix
     landed outside the pilot area, it takes you to what IS mapped -- easing filters
     would not put a single pin near that person. */
  if(youOutside){
    youOutside=false;
    panMap(0);
    setZoom(false, null);
    toast('Showing the mapped blocks in downtown Austin');
    return;
  }
  /* TICK-491: the kind-of-place selection eases with the rest. Leaving it set would
     empty the map again on the very next render and blame the wrong control. */
  filtFeats.clear(); filtCats.clear(); filtFresh='any'; filterApplied = personas.size>0;
  renderFilters(); updateFiltShow(); renderChipRow(); renderMap(); renderNearby();
  toast('Filters eased — showing this area again');
});

