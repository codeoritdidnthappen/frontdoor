function renderYouHere(W,H){
  /* WIRING. Round 15 gave the map a "where you are" mark, and drew it at LOC -- a
     constant, 2nd & Colorado -- so in the prototype the mark is always on the map and
     the pin group announces "Your location, 2nd & Colorado, is marked". That is the
     same false statement the locate button used to make -- the one the locate_real_fix
     op removed, and whose two forms WIRING_FORBIDDEN names so they cannot come back.
     It may not reach a page a person at a door reads: this service knows where
     somebody is only when the phone has told it.

     So the design keeps the drawing and this keeps the claim honest. The glyph is
     Round 15's, painted once and unchanged. The POSITION and the visibility come from
     placeYouHere() (tools/app_wiring/locate.js), which draws the mark only on a real
     geolocation fix, hides it when the fix is off the frame, and never invents one.
     The pin group says a location is marked only when one really is; the mark's own
     aria-hidden is Round 15's, and the group label is where it teaches. */
  const el = document.getElementById('you-here'); if(!el) return;
  if(!el.firstChild) el.innerHTML = youHereSVG();
  placeYouHere();
  const marked = !el.hidden;
  /* 7.7: the mark's state as text, on the group a screen reader actually lands on. */
  pinsEl.setAttribute('aria-label', marked
    ? 'Entrance pins on the map. Your location is marked on the map.'
    : 'Entrance pins on the map.');
}
