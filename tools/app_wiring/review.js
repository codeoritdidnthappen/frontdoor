/* the detected chips -- shared by the processing screen (5.5-6.5 s populate) and the review.
   Three sources, kept apart on purpose: verdicts the server actually returned; the staged
   examples, which are reachable only where there is no server at all; and, for a real run
   that failed, a sentence saying so. A failure never borrows the staged verdicts. */
function reviewChipsHTML(chipsOnly){
  if(liveResult){
    const crit=liveResult.assessment.criteria;
    const present=[], notSeen=[];
    LIVE_CRITERIA.forEach(key=>{
      const c=crit[key]; if(!c) return;
      const ck=EST_KEYMAP[key], conf=+c.confidence||0;
      if(c.verdict==='present')
        present.push(`<span class="fchip scan" style="cursor:default">${FEATS[ck].label}${dotTriple(conf,'var(--marigold-ink)')}</span>`);
      else notSeen.push(FEATS[ck].label);
    });
    if(chipsOnly) return present.join('');
    return (present.length?present.join(''):`<span class="vc-notseen">No features confirmed from this photo yet — it still helps.</span>`) +
      (notSeen.length?`<span class="vc-notseen">Not seen this time: ${notSeen.join(' · ')}</span>`:'');
  }
  if(liveSimulated()){
    const chips=STAGED.map(([k,c])=>
      `<span class="fchip scan" style="cursor:default">${FEATS[k].label}${dotTriple(c,'var(--marigold-ink)')}</span>`).join('');
    return chipsOnly ? chips : chips+`<span class="sim-tag">Simulated</span>`;
  }
  if(chipsOnly) return '';
  return `<span class="vc-notseen">No verdicts — ${esc(liveFailure())}. Publishing checks the photo again.</span>`;
}
function renderReviewChips(){
  document.getElementById('vc-chips').innerHTML = reviewChipsHTML(false);
}
function renderReview(){
  const art=document.getElementById('doorway-art2');
  const img=document.getElementById('captured-img');
  const band=document.getElementById('blurband');
  const tagText=document.getElementById('blur-tag-text');
  const note=document.getElementById('upload-note');
  const qNote=document.getElementById('quarantine-note');
  const hint=document.getElementById('review-hint');
  qNote.classList.remove('on'); qNote.textContent='';
  if(liveFrame){
    img.src=liveFrame.dataUrl; img.hidden=false;
    art.style.display='none'; band.style.display='none';
    note.classList.add('on');
    if(liveResult){
      const n=liveResult.faces_blurred|0;
      tagText.textContent = n>0 ? `${n} face${n===1?'':'s'} blurred at upload` : 'Blur checked at upload — no faces found';
      hint.textContent = 'Live verdicts from your photo — statements about what is visible, never measurements.';
      if(liveResult.quarantined){
        qNote.classList.add('on');
        qNote.textContent = 'Privacy hold: the automatic face check could not confirm every face is blurred, so this photo cannot be stored or published. Retake from further back, or publish to let the server check again.';
      }
    } else if(liveSimulated()){
      tagText.textContent='Simulated — nothing leaves this phone';
      note.classList.remove('on');   /* nothing is uploaded here, so nothing is blurred here */
      hint.textContent='This page was opened with no server to check the photo, so the chips are staged examples rather than anything read from it, and nothing will be published.';
    } else {
      /* say only what happened: on a transport failure or an early 503 the frame never
         reached the blur step, so "faces blurred at upload" would be its own small lie */
      tagText.textContent='Not checked — this photo has not left your phone';
      note.classList.remove('on');
      hint.textContent='The scan could not be completed — '+liveFailure()+'. Nothing was read from your photo. It is still here: publish to try again, or retake.';
    }
  } else {
    img.hidden=true; img.removeAttribute('src');
    art.style.display=''; band.style.display='';
    tagText.textContent='Auto-blur applied';
    note.classList.remove('on');
    hint.textContent='Simulated capture — no camera frame, so nothing will be published. Allow the camera or choose a photo to publish a real scan.';
  }
  document.getElementById('btn-publish').textContent = liveSimulated() ? 'Publish (simulated)' : 'Publish scan';
  renderEntranceField();
  renderReviewChips();
}
renderReviewChips();

