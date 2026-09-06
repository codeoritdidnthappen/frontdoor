/* ===================== live map data (same origin) =====================
   GET /map/data is the server's public pin list: the pre-catalogue merged with every published
   scan. Its pins merge into the embedded set by place_id and the server wins — a place the server
   marks verified (its Scanned tier) takes the server's verdicts, count and date, and a pin this
   page does not know is added. A place the server still lists as not-yet-checked keeps the
   embedded detail, which is the same estimate with its evidence text. No server, or a
   dataset_error, leaves the embedded pins exactly as they are. */
const OBS_TO_V = {visible:'present', not_visible:'not_visible'};
const inBBox = loc => loc.lat>=BBOX.lat0-0.001 && loc.lat<=BBOX.lat1+0.001 && loc.lng>=BBOX.lng0-0.001 && loc.lng<=BBOX.lng1+0.001;
function critFromChecklist(checklist, keymap){
  const crit={};
  (checklist||[]).forEach(c=>{
    if(!OBS_TO_V[c.observation]) return;
    const conf = typeof c.confidence==='number' ? (c.confidence<=1 ? c.confidence*100 : c.confidence) : 0;
    crit[keymap ? (keymap[c.key]||c.key) : c.key] = {v:OBS_TO_V[c.observation], c:Math.round(conf), e:''};
  });
  return crit;
}
function mergeServerPin(pin, base){
  const scanned = pin.state==='verified_accessible';
  const p = base || {id:String(pin.place_id), name:pin.name||'Entrance', lat:pin.location.lat, lng:pin.location.lng, crit:{}, tier:'est', date:pin.imagery_date||null};
  if(!base) places.push(p);
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

