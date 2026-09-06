/* ===================== corrections: the server's state, not a local echo =====================
   The design source seeded this list with three worked examples and the send button pushed a
   fourth into it. Nothing left the browser: the note appeared under "My corrections", which is
   what made it look received, and it died when the tab closed. That is TICK-387.

   So the list is not seeded and is not written by the send button. It is READ from the server:
     POST /correct           the suggestion itself (correct-send.js)
     GET  /correct/mine      this contributor's own corrections and their real status,
                             identified by the same X-Frontdoor-Contributor token the scan
                             path uses. 200 {corrections:[{correction_id, place_name,
                             category, scope, note, created_at, status, has_photo}]}
   Statuses are the server's: received (in the queue), reviewed, declined. A correction never
   changes a verdict, so none of these is one — they say where the note is, not what is true
   about the door.

   With no server (a file:// open) the list stays empty and says so, because there is nothing
   to read it from; a failed request says the list may be out of date rather than showing an
   empty tab as though nothing had ever been sent. */
const CORRECT_API = '/correct';
const corrections=[];
let correctionsFetch=null;
const CORRECTION_STATE={
  received:{cls:'review', label:'In review', sub:'In the review queue — a person reads every note'},
  reviewed:{cls:'added',  label:'Reviewed',  sub:'A reviewer has read this note'},
  declined:{cls:'photo',  label:'Closed',    sub:'Reviewed and closed — nothing on the map changed'}
};
const CORRECTION_CATEGORY={
  entrance_features:'Entrance features',
  business_identity:'Business name or location',
  photo_issue:'Photo issue',
  other:'Something else'
};
const CORRECTION_SCOPE={this_entrance:'this entrance', other_entrance:'a different entrance of this business'};
function correctionWhen(iso){
  const d=new Date(String(iso||''));
  if(isNaN(d)) return '';
  const days=Math.floor((Date.now()-d.getTime())/86400000);
  if(days<=0) return 'Today';
  if(days===1) return 'Yesterday';
  return d.toLocaleDateString(undefined,{month:'short',day:'numeric'});
}
/* one server record -> the row shape renderCorrections draws */
function correctionRow(c){
  const st=CORRECTION_STATE[c.status]||CORRECTION_STATE.received;
  const what=(CORRECTION_CATEGORY[c.category]||c.category||'Correction')
    +' · '+(CORRECTION_SCOPE[c.scope]||'this entrance')
    +(c.has_photo?' · photo attached':'');
  return {name:c.place_name||'Entrance', what, note:c.note||'', when:correctionWhen(c.created_at),
          status:st.cls, statusLabel:st.label, sub:st.sub};
}
function fetchMyCorrections(){
  return fetch(CORRECT_API+'/mine',{headers:{'X-Frontdoor-Contributor':contributorToken()}})
    .then(r=>r.ok?r.json():Promise.reject(r.status))
    .then(j=>{
      if(!j||!Array.isArray(j.corrections)) return;
      corrections.length=0;
      j.corrections.forEach(c=>corrections.push(correctionRow(c)));
      renderCorrections();
    })
    .catch(()=>{ toast("Couldn't reach the server — this list may be out of date"); });
}
/* Queued, not dropped: the refresh fired right after a successful send would
   otherwise be swallowed by a still-running one and the new note would not
   appear until the tab was reopened. */
function loadMyCorrections(){
  if(!HAS_SERVER) return;
  correctionsFetch = correctionsFetch
    ? correctionsFetch.then(fetchMyCorrections, fetchMyCorrections)
    : fetchMyCorrections();
  correctionsFetch.then(()=>{ correctionsFetch=null; });
}
