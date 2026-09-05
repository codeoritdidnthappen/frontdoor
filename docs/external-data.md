# External accessibility data (TICK-258, #242)

Round zero of the pre-catalogue seeds the map with license-clean external
accessibility data before any vision spend. This doc is the source of truth
for what each external source may and may not do, and for the pipelines that
are designed but not yet coded.

## Architecture rule (load-bearing)

External data NEVER feeds the vision model's input — the blind pass stays
blind, or we launder other databases' errors into "visually confirmed by AI".
External sources join AFTER assessment, in exactly three ways:

1. **Provenance stacking** — independent sources agreeing with the blind AI
   estimate render as additional provenance lines on a pin, always naming
   source and date ("Reported on OpenStreetMap - 2024").
2. **Disagreement queue** — vision-vs-external conflicts are logged
   internally in `data/external/disagreements.json` as scan priorities.
   Never displayed, never a public negative, never averaged away.
3. **Calibration at scale** — OSM tags as a noisy statistical reference for
   confidence calibration (business-level and stale; never truth for a
   single door).

**Never-negative guarantee**: an external `wheelchair=no` or
`wheelchair=limited` tag cannot change a public pin state and cannot render
publicly. `frontdoor.external_data` emits public provenance lines only for
agreeable reports; negative tags flow exclusively into the internal
disagreement queue. This is pinned by tests.

No external source ever upgrades a trust tier by itself.

## OpenStreetMap (shipped in round zero)

- **What**: nodes/ways in the demo bbox carrying `wheelchair=*`,
  `wheelchair:description=*`, or `entrance=wheelchair`, fetched via the
  Overpass API by `python -m frontdoor.external_data --refresh`.
- **License**: ODbL 1.0. Stored ONLY in the segregated side file
  `data/external/osm_accessibility.json`, with the attribution embedded in
  the file header and `source="openstreetmap"` on every record. Per the
  ODbL Collective Database Guideline this side table keeps our own dataset
  proprietary: OSM records are never merged into it.
- **Display**: matching pins (distance threshold + fuzzy name) gain
  provenance lines "Reported on OpenStreetMap - \<year\>" with
  "© OpenStreetMap contributors (ODbL)" attribution.
- **Refresh**: rerun the CLI; network calls happen only in the CLI path,
  never at import and never in tests.

## Wikimedia Commons imagery (shipped in round one)

- **What**: geotagged File-namespace photos in the demo bbox via the public
  Commons geosearch API (no key), fetched by `python -m
  frontdoor.external_data --refresh-commons`. The geosearch call MUST send
  `gsnamespace=6` — the default namespace returns zero imagery. A second
  batched `imageinfo`/`extmetadata` call per candidate supplies license,
  artist, dates, and URLs.
- **License gate**: only CC0 / CC BY / CC BY-SA (any version) survive
  ingest; NC, ND, unknown, and fair-use records are dropped with a counted
  reason before touching disk. CC BY / CC BY-SA records with no named
  artist are undisplayable and dropped too. Kept records live ONLY in the
  segregated side file `data/external/commons_imagery.json`, whose header
  carries the required-attribution statement and the CC BY-SA share-alike
  note.
- **Display**: pins within ~35 m of a kept photo gain a provenance line
  "Photo on Wikimedia Commons - \<year\> - \<license\> - \<artist\>"
  linking the Commons page. The radius is tighter than the OSM place
  radius, and no name matching applies, because Commons coordinates are
  photo positions (where the camera stood), not business positions. A
  photo line carries no accessibility claim — the never-negative rule is
  untouched.
- **Not yet**: no Commons image is assessed by the screening engine.
  Third-party imagery assessment is a follow-up round with its own
  matching QA; this round is ingest + provenance only.

## TDLR TABS (designed; code ships in round one — see `frontdoor.tabs` stub)

The Texas Architectural Barriers System is real, public, and worth an honest
badge. Texas requires a Registered Accessibility Specialist (RAS) plan
review + inspection for construction projects >= $50k under the Texas
Accessibility Standards, and the registry is searchable with
unauthenticated, server-rendered detail pages.

**Pipeline v1 (round one):**

1. **Public search**: query the TABS registry with city/county filters for
   the demo area; collect project IDs.
2. **Detail pages**: low-rate, robots.txt-respecting fetch of each project
   detail page. Fields: address, facility name, registration/inspection
   dates, estimated cost, scope of work, project status, RAS identity.
3. **Address matching**: normalize and match detail-page addresses to pin
   addresses; store matches in a segregated side file like the OSM one.
4. **Rendering**: "TAS accessibility inspection on record (TDLR, \<year\>) -
   project #\<id\>" — point-in-time and auditor-adjacent, never "verified
   accessible today". The record attaches to the construction project, not
   the current tenant; the Austin certificate-of-occupancy dataset detects
   tenant turnover under a record.
5. **Bulk path**: there is no API; bulk extraction is a Texas Public
   Information Act request (template below).

**Honesty limits**: status only — no inspection outcome detail; never
current-state verification; never the auditor trust tier (cut from v1 per
the #73 design thread).

### Drafted PIA request template (bulk extract)

> To: Public Information Coordinator, Texas Department of Licensing and
> Regulation \<address/email from TDLR's current open-records page\>
>
> Re: Public Information Act request — Architectural Barriers project data
>
> Under the Texas Public Information Act (Tex. Gov't Code Chapter 552), I
> request an electronic copy (CSV or similar machine-readable format) of
> the following fields for all Architectural Barriers (TABS) projects
> located in Travis County registered on or after January 1, 2015:
>
> - TABS project number; project name and facility name
> - Project street address, city, county, ZIP
> - Registration date, plan review date(s), inspection date(s)
> - Estimated construction cost and scope/type of work
> - Current project status
> - Name and registration number of the Registered Accessibility
>   Specialist of record
>
> This request is limited to information already published on individual
> TABS project detail pages; I am requesting it in bulk electronic form.
> If any portion is excepted from disclosure, please release the remainder
> and cite the exception. Please contact me with the estimated cost if
> charges will exceed $40.
>
> Requested by: \<name\>, \<email\>, \<date\>

## Foursquare OS Places and Austin open data (round one)

- **Foursquare OS Places**: Apache-2.0 monthly Parquet POI backbone — fully
  storable and the ID spine we own. No accessibility fields. Ingest is
  round-one scope.
- **Austin open data (SODA API, unrestricted)**: sidewalk/curb-ramp
  inventory with condition grades and ADA fields, permits, certificates of
  occupancy. Planned as route-context provenance where within a block of a
  pin; the CO dataset also detects tenant turnover under a TABS record.
  Round-one scope.

## Google Places and Yelp: display-time only, never ingested

- **Google Places (New)** `accessibilityOptions` (including
  `wheelchairAccessibleEntrance`) is entrance-specific and useful — but the
  Places ToS forbids storing anything except `place_id`. It may only ever
  be a display-time overlay fetched at render, with required attribution.
  **Nothing from it enters our database or any file in this repo.**
- **Yelp Fusion** owner-set attributes: 24-hour cache maximum, no free
  tier. Same display-time-only posture if adopted at all.

Consequently `frontdoor.external_data` contains no Google/Yelp ingest and
must never grow one; a display-time overlay, if built, lives entirely in
the page's render path.

The pre-catalogue is the exception, and it is a known one: `name` and
`location` from Places sit in `data/precatalogue.json` and in the Second
Street district rows of `data/precatalogue_census.json`, against the
criterion above. #242 owns that and has not settled it. Work since has
been held to not deepening it — the census rows the Congress Avenue sweep
added under #346 hold the `place_id` alone, and the names they were
matched on were resolved in the same pass and never written down.

## Files

| File | Status | Contents |
| --- | --- | --- |
| `data/external/osm_accessibility.json` | public-safe, segregated, ODbL-attributed | OSM wheelchair/entrance records for the demo bbox |
| `data/external/entrance_anchors.json` | public-safe, segregated, ODbL-attributed | Nominatim geocodes of the street numbers read at the captured entrances, so the entrance-to-place distance gate (#346) has a door position to measure from. Only an address the operator actually read is geocoded, never a business name |
| `data/external/commons_imagery.json` | public-safe, segregated, per-record CC license + artist | open-licensed Wikimedia Commons photo records for the demo bbox |
| `data/external/disagreements.json` | INTERNAL ONLY | external-vs-AI conflicts as scan priorities; never rendered |
