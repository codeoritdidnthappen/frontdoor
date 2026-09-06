"""The served page is BUILT from the design source, and the wiring survives the build.

`src/frontdoor_server/app.html` is not edited. `tools/port_app_page.py` takes the design
source committed under `design-source/` and applies this service's wiring to it as an
ordered set of anchored edits. These tests pin the four properties that make that a
mechanism rather than a one-off copy:

  * the page on disk is exactly what the port produces (nobody hand-edited it back);
  * the port is byte-identical on a second run;
  * a change in the design source reaches the page with no hand editing;
  * the wiring survives the port, and a design change that moves an anchor fails loudly
    instead of quietly dropping the wiring behind it.

Everything the wiring itself has to say to a user or a server is pinned in
tests/test_app_page.py, against the served bytes.
"""

import pytest

from tools.port_app_page import (
    DESIGN_SOURCE,
    OPS,
    SERVED_PAGE,
    WIRING_FORBIDDEN,
    WIRING_REQUIRED,
    PortError,
    main,
    port,
)


@pytest.fixture(scope="module")
def design_source():
    return DESIGN_SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.fixture(scope="module")
def ported(design_source):
    page, _ = port(design_source)
    return page


def test_the_served_page_is_exactly_what_the_port_produces(ported):
    """A hand edit to app.html is a change that the next design round silently reverts."""
    served = SERVED_PAGE.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert served == ported, (
        "src/frontdoor_server/app.html is not what tools/port_app_page.py produces from "
        "the committed design source. Re-run `python tools/port_app_page.py`, and put any "
        "change you made by hand into the design source or into tools/app_wiring/."
    )


def test_the_port_is_byte_identical_on_a_second_run(design_source, ported):
    again, _ = port(design_source)
    assert again.encode("utf-8") == ported.encode("utf-8")


def test_the_wiring_survives_a_port(ported):
    for needle in WIRING_REQUIRED:
        assert needle in ported, f"the port dropped wiring: {needle!r}"
    for needle in WIRING_FORBIDDEN:
        assert needle not in ported, f"the port let design-only wiring through: {needle!r}"


def test_a_failed_scan_still_cannot_borrow_the_simulated_verdicts(ported):
    """The defect this port must never reintroduce (see tests/test_app_page.py).

    Pinned on the port's own output as well as on the served bytes, so a design source
    that rewrites the scan flow cannot bring the old silent fallback back with it.
    """
    predicate = ported.split("const liveSimulated =", 1)[1].split("\n", 1)[0]
    assert "HAS_SERVER" in predicate
    assert "liveNetFail" not in predicate
    simulated = ported.split("\n  if(simulated){", 1)[1].split("\n  } else {", 1)[0]
    assert "upgradePin(" not in simulated
    assert "placeForRef(" not in simulated


def test_a_change_in_the_design_source_reaches_the_page(design_source):
    """The whole point: a design round flows through without anyone editing app.html."""
    marker = "This is exactly what neighbors will see."
    assert design_source.count(marker) == 1
    changed = design_source.replace(marker, "This is exactly what your neighbours will see.")
    page, _ = port(changed)
    assert "This is exactly what your neighbours will see." in page
    assert marker not in page
    for needle in WIRING_REQUIRED:  # ...and the wiring is still all there
        assert needle in page


def test_a_moved_anchor_fails_the_port_instead_of_dropping_the_wiring(design_source):
    """A design change the ops cannot find must stop the build, not ship a page without it."""
    op = next(o for o in OPS if o.name == "live_screening")
    broken = design_source.replace(op.anchor, "/* the design source renamed this section */")
    with pytest.raises(PortError) as excinfo:
        port(broken)
    assert "live_screening" in str(excinfo.value)
    assert "matches 0 times" in str(excinfo.value)


def test_an_op_that_stops_doing_its_job_fails_the_port(design_source, monkeypatch):
    """The anchors can all still match while the wiring behind one has gone missing."""
    monkeypatch.setattr(
        "tools.port_app_page.WIRING_REQUIRED",
        list(WIRING_REQUIRED) + ["a line no fragment carries"],
    )
    with pytest.raises(PortError) as excinfo:
        port(design_source)
    assert "wiring missing" in str(excinfo.value)


def test_every_op_says_why_the_wiring_cannot_live_in_the_design(design_source):
    """An op with no reason on it is the next one somebody deletes as mysterious."""
    for op in OPS:
        assert op.why.strip(), f"op {op.name!r} has no reason recorded"
        assert design_source.count(op.anchor) == 1, (
            f"op {op.name!r} does not anchor exactly once in the committed design source"
        )


def test_the_check_mode_passes_on_the_committed_page(capsys):
    assert main(["--check"]) == 0
    assert "up to date" in capsys.readouterr().out


def test_the_check_mode_fails_on_a_page_the_port_did_not_produce(tmp_path, capsys):
    stale = tmp_path / "app.html"
    stale.write_text("<html>hand-edited</html>", encoding="utf-8")
    assert main(["--check", "--out", str(stale)]) == 1
    assert "re-run tools/port_app_page.py" in capsys.readouterr().err


def test_the_port_writes_the_same_bytes_it_returns(tmp_path, ported):
    out = tmp_path / "app.html"
    assert main(["--out", str(out)]) == 0
    assert out.read_bytes() == ported.encode("utf-8")
    assert main(["--out", str(out)]) == 0
    assert out.read_bytes() == ported.encode("utf-8")
