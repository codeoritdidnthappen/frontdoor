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

/* ---- the four answers --------------------------------------------------------- */
function onGeoFix(pos){
  geoState='ok';
  clearGeoAlert();
  youFix={lat:pos.coords.latitude, lng:pos.coords.longitude};
  const km=kmApart(youFix, pilotCentre());
  paintLocateBtn();
  if(inPilot(youFix)){
    youOutside=false; youAway='';
    panMap(0);
    setZoom(false, youFix);          /* re-renders, which draws the mark on the fix */
    toast('Centered on you — you are marked on the map');
  } else if(km<=GEO_NEAR_KM){
    /* just outside: the frame moves as close to the fix as the pilot bbox allows,
       and the toast says that rather than claiming a centre it does not have */
    youOutside=false; youAway=awayLabel(km);
    panMap(0);
    setZoom(false, youFix);          /* clamped to the pilot bbox by clampCentre */
    toast('You are just outside the mapped blocks — showing the nearest of them');
  } else {
    /* far out: the map does not move, because there is nothing of ours to move it to */
    youOutside=true; youAway=awayLabel(km);
    renderMap();
    toast('EntryMap has not mapped your area yet');
  }
}
/* Every way of not getting a fix ends here, and every one of them clears what the
   LAST attempt left on the map. Without that, the mark from an earlier fix stays
   drawn -- "You are here" over a point nothing has confirmed -- beside a control
   that has just said we do not know where you are, and the out-of-area invite keeps
   quoting a distance from a fix we no longer have. The re-render takes both down; a
   filter that legitimately empties the map keeps its own invite, because
   paintEmptyInvite still asks about the pins. */
function geoStopped(state, short, why){
  geoState=state;
  paintLocateBtn();
  toast(short);
  geoAlert(why);
  youOutside=false;
  renderMap();
}
function sayDenied(){
  geoStopped('denied', 'Location is off for this site',
    'Location is off for this site, so the map has not moved and shows the pilot area '
    +'in downtown Austin. You can turn location back on for this site in your browser '
    +'settings.');
}
function onGeoFail(err){
  const code = err && err.code;
  if(code===1){                                   /* PERMISSION_DENIED */
    sayDenied();
  } else if(code===3){                            /* TIMEOUT */
    geoStopped('unavailable', 'Finding your location timed out',
      'Finding your location took too long, so the map has not moved. '
      +'Tap the location button to try again.');
  } else {                                        /* POSITION_UNAVAILABLE */
    geoStopped('unavailable', 'Your location is not available',
      'Your device could not work out where it is, so the map has not moved. '
      +'Trying again, or outdoors, often works.');
  }
}

function locateMe(){
  if(geoState==='asking') return;              /* one request at a time */
  closeSheets();
  /* the two cases where there is nothing to ask. Checked BEFORE getCurrentPosition,
     because a browser answers "denied" for an insecure page, and being told the
     permission was refused when it was never offered is the wrong thing to act on. */
  if(!navigator.geolocation){
    geoStopped('unavailable', 'This browser cannot share a location',
      'This browser cannot share a location, so the map has not moved and shows the '
      +'pilot area in downtown Austin.');
    return;
  }
  if(!window.isSecureContext || location.protocol==='file:'){
    geoStopped('unavailable', 'Location needs a secure connection',
      'This page is not on a secure connection, so the browser will not share a '
      +'location. The map has not moved.');
    return;
  }
  if(geoState==='denied'){                     /* answered already; never ask twice */
    sayDenied();
    return;
  }
  geoState='asking'; paintLocateBtn();
  toast('Finding your location…');
  navigator.geolocation.getCurrentPosition(onGeoFix, onGeoFail, GEO_OPTS);
}
document.getElementById('locate-btn').addEventListener('click', locateMe);

/* If the browser will tell us the standing permission without prompting, the control
   is named correctly before it is ever pressed, and a user who turns location back on
   in site settings gets a control that asks again instead of one that keeps repeating
   the refusal. Reading this state prompts nobody and fetches no position. */
if(navigator.permissions && navigator.permissions.query){
  navigator.permissions.query({name:'geolocation'}).then(st=>{
    const sync=()=>{
      if(st.state==='denied'){ geoState='denied'; youOutside=false; youFix=null; }
      else if(geoState==='denied'){ geoState='idle'; }
      paintLocateBtn(); renderMap();
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
  filtFeats.clear(); filtFresh='any'; filterApplied = personas.size>0;
  renderFilters(); updateFiltShow(); renderChipRow(); renderMap(); renderNearby();
  toast('Filters eased — showing this area again');
});

