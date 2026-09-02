"""The app's seed and the committed seed must be one value (TICK-025 AC2).

The capture app ships without the Python package, so the seed is duplicated into Swift. A build
carrying a different seed assigns a different set of folds -- self-consistently, and completely
wrong. Nothing at runtime would notice: every entrance still gets a split, the app still works,
and the sealed set quietly stops being the sealed set.

The ticket asks for exactly this check: "a build whose seed does not match the committed seed
fails a test." Here rather than in XCTest, because CI runs on Linux with no Xcode.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFT = ROOT / "ios" / "FrontdoorCapture" / "Truth" / "SplitAssignment.swift"
SEED_FILE = ROOT / "src" / "frontdoor" / "split_seed.json"


def swift_constant(name: str) -> str:
    source = SWIFT.read_text(encoding="utf-8")
    match = re.search(rf'static let {name} = "?([^"\n]+)"?', source)
    assert match, f"{name} not found in {SWIFT.name}"
    return match.group(1).strip()


def test_the_app_seed_is_the_committed_seed():
    committed = json.loads(SEED_FILE.read_text(encoding="utf-8"))["seed"]
    assert swift_constant("seed") == committed


def test_the_app_bucket_boundaries_match_the_tool():
    from frontdoor.split import CALIB_PERCENT, SEALED_PERCENT

    assert int(swift_constant("sealedPercent")) == SEALED_PERCENT
    assert int(swift_constant("calibPercent")) == CALIB_PERCENT


def test_the_golden_vectors_still_describe_the_tool():
    """The fixture both suites read cannot be allowed to rot.

    Swift asserts against this file; if the Python tool changed and the file did not, Swift would
    be pinned to an answer the analysis no longer gives.
    """
    from frontdoor.split import assign_split

    golden = json.loads(
        (ROOT / "tests" / "fixtures" / "split_golden.json").read_text(encoding="utf-8")
    )
    assert len(golden["vectors"]) >= 20, "AC asks for at least 20 shared IDs"
    for row in golden["vectors"]:
        assert assign_split(row["entrance_id"]) == row["split"], row

    # A fixture that is all one split would pass while proving nothing about the boundaries.
    assert len({row["split"] for row in golden["vectors"]}) == 3


def test_the_app_never_shows_the_operator_a_split():
    """AC6: the operator is not shown whether an entrance is sealed.

    Someone who knows a doorway is in the test set photographs it more carefully without deciding
    to, and that is exactly the bias the sealed split exists to exclude (D-007).
    """
    ui = ROOT / "ios" / "FrontdoorCapture" / "UI"
    for path in sorted(ui.glob("*.swift")):
        code = "\n".join(
            re.sub(r"//.*", "", line) for line in path.read_text(encoding="utf-8").splitlines()
        )
        assert ".split" not in code, f"{path.name} reads a split into the UI layer"
        assert "Split." not in code, f"{path.name} names a split case in the UI layer"
