"""TDLR TABS (Texas Architectural Barriers System) pipeline — round-one stub.

Round zero of TICK-258 (#242) ships no TABS code, only this stub and the
pipeline design in docs/external-data.md. What round one will implement:

- The TDLR TABS registry is public and searchable (city/county filters)
  with unauthenticated, server-rendered project detail pages: address,
  facility name, dates, estimated cost, scope, status, and the Registered
  Accessibility Specialist of record. robots.txt permits polite fetching;
  there is no API, and bulk data means a Texas Public Information Act
  request (template drafted in docs/external-data.md).
- Ingest will be a low-rate fetch of detail pages for demo-area addresses,
  address-matched to pins, stored SEGREGATED like the OSM side file, and
  rendered as an honest point-in-time provenance line:
  "TAS accessibility inspection on record (TDLR, <year>) - project #<id>".
- Honesty limits (load-bearing): a TABS record is a plan review/inspection
  attached to a construction project, not to the current tenant, and it
  carries status only — it is never "verified accessible today", never a
  trust-tier upgrade, and certificate-of-occupancy data is needed to detect
  tenant turnover under a record.
"""
