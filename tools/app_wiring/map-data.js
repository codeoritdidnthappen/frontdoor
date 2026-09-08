/* ===================== live map data (same origin) =====================
   GET /map/data is the server's public pin list: the pre-catalogue merged with every published
   scan. Its pins merge into the embedded set by place_id and the server wins — a place the server
   marks scanned on-site (its Scanned tier) takes the server's verdicts, count and date, and a pin this
   page does not know is added. A place the server still lists as not-yet-checked keeps the
   embedded detail, which is the same estimate with its evidence text. No server, or a
   dataset_error, leaves the embedded pins exactly as they are.
   needs_relook rides along on a pin: freshness only, never a state and never a verdict. */
const OBS_TO_V = {visible:'present', not_visible:'not_visible'};
const inBBox = loc => loc.lat>=BBOX.lat0-0.001 && loc.lat<=BBOX.lat1+0.001 && loc.lng>=BBOX.lng0-0.001 && loc.lng<=BBOX.lng1+0.001;
function critFromChecklist(checklist, keymap){
  const crit={};
  (checklist||[]).forEach(c=>{
    if(!OBS_TO_V[c.observation]) return;
    /* TICK-462: /map/data carries exactly one confidence scale and says so on the
       payload -- a percentage from 0 through 100, the scale the engine answers on.
       This line used to multiply anything <= 1 by 100: a reader coping with a
       producer that rescaled, which is what let the field mean two different
       things depending on which record it came from. The producer is fixed
       (frontdoor.scan_records._scan_criteria), so the value is taken as served. */
    const conf = typeof c.confidence==='number' ? c.confidence : 0;
    crit[keymap ? (keymap[c.key]||c.key) : c.key] = {v:OBS_TO_V[c.observation], c:Math.round(conf), e:''};
  });
  return crit;
}
function mergeServerPin(pin, base){
  const scanned = pin.state==='scanned_on_site';
  const p = base || {id:String(pin.place_id), name:pin.name||'Entrance', lat:pin.location.lat, lng:pin.location.lng, crit:{}, tier:'est', date:pin.imagery_date||null};
  if(!base) places.push(p);
  /* TICK-387: corroborated corrections say the world may have moved. It is a FRESHNESS
     flag and nothing else -- the tier, the state and every check below are read from the
     same pin exactly as before -- and the card turns it into the existing
     "Could you take another look?" nudge, which asks for a photo and claims nothing. */
  p.relook = pin.needs_relook===true;
  if(scanned){
    if(p.tier==='est') p.tier='scan';
    p.live=true;
    p.views=pin.scan_count||p.views||1;
    p.crit=critFromChecklist(pin.checklist, LIVE_TO_DOOR);
    p.date=pin.last_scanned||pin.imagery_date||p.date||'';
  } else if(!base){
    p.crit=critFromChecklist(pin.checklist, null);
  }
  p.f=featsOf(p);
}
function loadLiveMap(){
  fetch('/map/data',{headers:{'Accept':'application/json'}})
    .then(r=>r.ok?r.json():null)
    .then(j=>{
      if(!j||!Array.isArray(j.pins)) return;
      if(j.dataset_error) console.info('EntryMap: /map/data carries no dataset ('+j.dataset_error+') — embedded pins plus any published scans');
      /* TICK-370: this page is where a contributor looks after publish. scans_error
         means the store their scan went into is unreachable, so the pin they expect
         is simply not there. Toast the subsystem; the server's string quotes a path
         and this page is public. dataset_error stays console.info — embedded pins
         still draw. */
      if(j.scans_error) toast('Published scans could not be loaded');
      else if(j.scans_skipped) toast(j.scans_skipped===1
        ? '1 published scan could not be read'
        : j.scans_skipped+' published scans could not be read');
      const byId=new Map(places.map(p=>[p.id,p]));
      let merged=0;
      j.pins.forEach(pin=>{
        if(!pin||!pin.location) return;
        const base=byId.get(String(pin.place_id));
        if(!base && !inBBox(pin.location)) return;   /* the map draws the demo area only */
        mergeServerPin(pin, base); merged++;
      });
      if(merged){ renderMap(); renderNearby(); }
    })
    .catch(()=>{});  /* no server (file://, offline): embedded pins only */
}

