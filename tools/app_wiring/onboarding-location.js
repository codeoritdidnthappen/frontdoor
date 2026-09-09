/* ===================== onboarding: the location step asks, and says what it heard =====
   THE DEFECT THIS REPLACES. The step's "Allow location" control flipped #loc-toggle
   on, set aria-checked="true" and advanced to the next step. It never called
   navigator.geolocation. Nothing was asked, no permission was granted, and the
   interface then stated that location was allowed -- visually and to a screen reader
   -- as the first thing a new user is told and the last thing they would think to
   doubt. (Both lines are in WIRING_FORBIDDEN in tools/port_app_page.py, so a design
   refresh either carries this handler or fails the port loudly.)

   #487 was the same defect on the map's locate control: a control that stages the
   APPEARANCE of an outcome instead of producing it. That one made a false claim about
   a place. This one made a false claim about a permission.

   THE SHARED PART. Which of the eight outcomes happened is decided by askGeo() in
   tools/app_wiring/locate.js, and only there -- this step passes it a `say` function
   and is handed the answer. Nothing here calls navigator.geolocation, nothing here
   re-derives denied from timed out, and nothing here writes #loc-toggle: the switch is
   painted from the recorded permission by paintLocToggle(), so its state and its
   aria-checked are a function of what the browser said and never of the tap.

   WHAT IS SPECIFIC TO ONBOARDING. The step is skippable by design, so no answer may
   block it. A refusal is accepted rather than argued with, the sentence says plainly
   what will be different without a location, and the button under it names the way
   onward -- "Try again" only where trying again is a real possibility, never after a
   denial, which is an answer. */

const obAllowBtn = document.getElementById('ob-allow-loc');
const obLocLine  = document.querySelector('#ob-location .ob-p');
const OB_LOC_ASK_LABEL = obAllowBtn ? obAllowBtn.textContent : 'Allow location';
/* what the primary button does now: ask the browser, or carry on without a location */
let obAllowDoes = 'ask';

/* Each outcome's own true sentence, in the step's voice. The map's wording for the
   same outcomes says "the map has not moved", which is the wrong tense here: on this
   step nothing has been shown yet, so what is said is what will be different. */
const OB_LOC_SAID = {
  'no-api': {
    say: ()=>'This browser cannot share a location, so the map will open on the few '
      +'blocks of downtown Austin this pilot covers, and distances will be measured '
      +'from there.',
    btn: 'Continue without location', does: 'go'
  },
  insecure: {
    say: ()=>'This page is not on a secure connection, so the browser will not share a '
      +'location. The map will open on the few blocks of downtown Austin this pilot '
      +'covers, and distances will be measured from there.',
    btn: 'Continue without location', does: 'go'
  },
  denied: {
    say: ()=>'Location is off for this site, so nothing was shared and the map will '
      +'open on the few blocks of downtown Austin this pilot covers rather than on '
      +'you. You can turn location on for this site in your browser settings.',
    btn: 'Continue without location', does: 'go'
  },
  timeout: {
    say: ()=>'Finding your location took too long, so nothing was shared. You can try '
      +'again, or choose an area instead and the map will open on the blocks this '
      +'pilot covers.',
    btn: 'Try again', does: 'ask'
  },
  unavailable: {
    say: ()=>'Your device could not work out where it is, so nothing was shared. '
      +'Trying again, or being outdoors, often works — or choose an area instead.',
    btn: 'Try again', does: 'ask'
  },
  /* granted, but a long way from the pilot area: the permission is real and the switch
     is genuinely on, and there is still nothing near you to show. Both are true and
     both are said. */
  far: {
    say: ()=>'Location is on. You are '+youAway+' the few blocks of downtown Austin '
      +'this pilot covers, so there is nothing mapped near you yet — the map will open '
      +'on the blocks we have mapped. That is what we have mapped; it says nothing '
      +'about the places around you.',
    btn: 'Continue', does: 'go'
  }
};

function obLocBusy(on){
  if(!obAllowBtn) return;
  obAllowBtn.setAttribute('aria-busy', on ? 'true' : 'false');
  if(on) obAllowBtn.textContent='Finding your location…';
}

/* The step's half of the answer. The switch is not touched here; it has already been
   painted from the recorded permission. */
function obLocSays(o){
  if(o.kind==='granted' && o.where!=='far'){
    /* the two outcomes with nothing to explain: the permission is on and the map has
       somewhere real to open on. The frame is MOVED here, not merely promised --
       finishOnboarding() only renders, so without this the map opens on the pilot bbox
       and "the map will center on you" is the same kind of sentence this ticket is
       about: a claim staged rather than produced. Being just outside the mapped blocks
       is not being centred on, because clampCentre holds the frame inside the bbox, so
       that case says what it will really do instead. */
    setZoom(false, youFix);
    obLocBusy(false);
    if(obAllowBtn) obAllowBtn.textContent=OB_LOC_ASK_LABEL;
    obAllowDoes='ask';
    toast(o.where==='inside'
      ? 'Location is on — the map will center on you'
      : 'Location is on — you are just outside the mapped blocks, so the map will open '
        +'on the nearest of them');
    showScreen('ob-needs');
    return;
  }
  const said = OB_LOC_SAID[o.kind==='granted' ? 'far' : o.kind];
  const sentence = said.say();
  obLocBusy(false);
  if(obLocLine) obLocLine.textContent=sentence;
  /* an answer the person did not get is an error condition, so it reaches the same
     role="alert" region the map control uses rather than only changing on screen */
  geoAlert(sentence);
  if(obAllowBtn) obAllowBtn.textContent=said.btn;
  obAllowDoes=said.does;
}

function obAllowTap(){
  if(obAllowDoes==='go'){ showScreen('ob-needs'); return; }
  obLocBusy(true);
  /* 'answered' means askGeo already ran obLocSays synchronously -- a remembered
     denial, no API, or an insecure page. A denial is never asked again. */
  if(askGeo(obLocSays)==='busy') obLocBusy(false);
}
if(obAllowBtn) obAllowBtn.addEventListener('click', obAllowTap);

/* "Choose an area instead": never a dead end -- the search field opens as soon as
   onboarding lands on the map. It does not write the switch either way: it is not an
   answer about the permission, and a person who granted location and then chose an
   area still has it granted. */
document.getElementById('ob-loc-notnow').addEventListener('click',()=>{
  openSearchAfterOnboarding=true;
  toast('No problem — pick an area by search');
  showScreen('ob-needs');
});
