function startScan(fromCard, opts){
  cancelScanTimers();
  resetLive();
  fromLibrary=false;
  ownerAttest=!!(opts && opts.ownerAttest);
  document.getElementById('btn-library').hidden=ownerAttest;
  scanFromCard=!!fromCard;
  if(!scanFromCard){ /* no card: the nearest estimated pin stands in for the doorway art; the real place is named at review */
    const next = places.filter(p=>p.tier==='est').sort((a,b)=>(Math.hypot(a.lat-cx,a.lng-cy)-Math.hypot(b.lat-cx,b.lng-cy)))[0];
    if(next) scanTarget=next;
  }
  document.getElementById('scan-target').innerHTML = scanFromCard
    ? `Scanning · <b>${esc(scanTarget.name)}</b>`
    : `Scanning near you · <b>name the entrance after the photo</b>`;
  document.getElementById('entrance-name').value='';
  paintDoorway();
  showScreen('scan-primer');
}
document.querySelectorAll('[data-scan-exit]').forEach(b=>b.addEventListener('click',()=>{
  cancelScanTimers(); resetLive(); geoFix=null; ownerAttest=false; fromLibrary=false;
  document.getElementById('btn-library').hidden=false;
  showScreen('screen-map'); renderMap();
}));
document.getElementById('btn-allow-cam').addEventListener('click',()=>{
  showScreen('scan-capture');
  tryStartCamera(); /* live viewfinder when granted; the illustrated capture stays otherwise */
  requestGeoFix();  /* places the scan when it was not launched from a card */
});
document.getElementById('btn-shutter').addEventListener('click',async ()=>{
  if(camStream){
    const frame=await captureFrame();
    stopCamera();
    if(frame){ liveFrame=frame; startLiveUpload(frame); }
    else resetLive();
  } else resetLive();
  /* ROUND 9, V20 beat 1: the white shutter wash. The frame is already captured, so
     the wash is over a frozen image, which is what a shutter looks like. Under
     reduced motion there is no wash and no wait -- a flash IS the motion here, and
     nothing depends on it: the capture is confirmed by the processing screen, its
     progressbar and its live region.
     Carried verbatim from the design source, which owns this beat; this handler is
     inside the region the scan_entry op replaces, so the beat only reaches the served
     page through here. */
  const wash=document.getElementById('shutter-wash');
  if(isReduced()){
    showScreen('scan-processing'); runProcessing();
  } else {
    wash.classList.remove('on'); void wash.offsetWidth; wash.classList.add('on');
    after(180,()=>{ wash.classList.remove('on'); showScreen('scan-processing'); runProcessing(); });
  }
});
document.getElementById('btn-retake').addEventListener('click',()=>{
  const wasLive=!!liveFrame;
  resetLive();
  showScreen('scan-capture');
  if(wasLive) tryStartCamera();
});

