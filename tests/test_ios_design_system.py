"""The Swift design layer must not drift from the approved asset library.

`ios/FrontdoorCapture/UI/DesignSystem/` restates the library's tokens in Swift, because an iOS app
cannot read JSON at layout time. A restatement is a copy, and a copy drifts. CI never builds Swift
-- there is no Mac on it -- so, in the shape of `test_ios_capture_privacy.py`, the rules that must
hold are read out of the sources instead.

What each test pins is the thing that would be invisible if it broke: a colour that is no longer
the approved colour, a pin that is the wrong size for its context, a duration that no longer
matches the motion tokens, an icon quietly redrawn by hand, a reduced-motion path that shortens
instead of stopping, or an unavailable control that has gone grey.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "docs" / "design" / "entrymap"
SVG = TOKENS / "svg"
LAYER = ROOT / "ios" / "FrontdoorCapture" / "UI" / "DesignSystem"
PRIMER = ROOT / "ios" / "FrontdoorCapture" / "UI" / "ScanPrimerView.swift"
SCREENS_DIR = ROOT / "ios" / "FrontdoorCapture" / "UI"


def screens():
    """Every screen outside the design system layer.

    A glob rather than a list, deliberately. A list is a thing you forget to add to, and the
    twelfth screen is the one that would have quietly stayed on SwiftUI defaults (#367).
    """
    return sorted(SCREENS_DIR.glob("*.swift"))
PROJECT = ROOT / "ios" / "project.yml"


def read(path):
    return path.read_text(encoding="utf-8")


def design_tokens():
    return json.loads(read(TOKENS / "design-tokens.json"))


def motion_tokens():
    return json.loads(read(TOKENS / "interaction-motion.json"))


def pin_tokens():
    return json.loads(read(TOKENS / "pin-hierarchy.json"))


# --------------------------------------------------------------------------- colour


def test_the_palette_is_the_eleven_official_colours_and_nothing_else():
    source = read(LAYER / "EntryMapPalette.swift")
    declared = dict(
        re.findall(r"static let (\w+) = Color\(entryMapHex: 0x([0-9A-F]{6})\)", source))
    official = {name: value.lstrip("#").upper()
                for name, value in design_tokens()["color"].items()}
    assert declared == official, (
        "the palette and the token file disagree; the token file is the one that is right"
    )


def test_no_hex_colour_is_spelled_outside_the_palette():
    """One place knows what the colours are. Anywhere else is a colour nobody approved."""
    offenders = {}
    for swift in sorted(LAYER.glob("*.swift")) + screens():
        if swift.name == "EntryMapPalette.swift":
            continue
        body = "\n".join(re.sub(r"//.*", "", line) for line in read(swift).splitlines())
        found = re.findall(r"Color\(|0x[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{6}\b", body)
        # `Color(entryMapHex:)` is fileprivate to the palette, so any `Color(` here is a raw one.
        if found:
            offenders[swift.name] = found
    assert offenders == {}, f"colours spelled outside the palette: {offenders}"


def wcag_ratio(foreground, background):
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    def luminance(hexcolour):
        r, g, b = (int(hexcolour[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def approved_pairings():
    """The contrast report's table, as {(foreground, background): stated ratio}."""
    rows = {}
    for line in read(TOKENS / "contrast-report.md").splitlines():
        found = re.findall(r"`#([0-9A-Fa-f]{6})`", line)
        ratio = re.search(r"\|\s*([\d.]+):1\s*\|", line)
        if len(found) == 2 and ratio:
            rows[(found[0].upper(), found[1].upper())] = float(ratio.group(1))
    return rows


def test_the_contrast_report_is_arithmetically_true():
    """If the report is wrong, every pairing built on it is wrong too."""
    rows = approved_pairings()
    assert len(rows) >= 7, "the contrast report's table did not parse"
    for (foreground, background), stated in rows.items():
        actual = wcag_ratio(foreground, background)
        assert abs(actual - stated) < 0.02, (
            f"#{foreground} on #{background} is {actual:.2f}:1, the report says {stated}:1")


def test_every_semantic_pairing_the_layer_uses_is_an_approved_one():
    """A role pair the report never approved is a contrast decision made by accident."""
    colours = {name: value.lstrip("#").upper()
               for name, value in design_tokens()["color"].items()}
    source = read(LAYER / "EntryMapPalette.swift")
    roles = dict(re.findall(r"static let (\w+) = (\w+)\n", source))
    # foreground role, background role -- the pairings the layer actually paints.
    pairs = [
        ("ink", "card"), ("ink", "ground"), ("subduedInk", "card"),
        ("onDarkGround", "darkGround"), ("onViolet", "violet600"), ("onMarigold", "marigold400"),
    ]
    approved = approved_pairings()
    for foreground, background in pairs:
        fg = colours[roles.get(foreground, foreground)]
        bg = colours[roles.get(background, background)]
        assert (fg, bg) in approved or (bg, fg) in approved, (
            f"{foreground} on {background} (#{fg} on #{bg}) is not a pairing the contrast "
            "report approves")


# --------------------------------------------------------------------------- type


def test_every_step_of_the_scale_scales_with_dynamic_type():
    source = read(LAYER / "EntryMapTypography.swift")
    steps = re.findall(r"static let (\w+) = EntryMapTextStyle\((.*?)\)\n", source, re.S)
    assert len(steps) >= 10, "the type scale did not parse"
    for name, body in steps:
        assert "relativeTo:" in body, f"{name} is a fixed point size"


def test_the_numeric_steps_are_tabular_and_the_rest_are_not():
    """Atkinson's figures are proportional. A column of them set in the wrong step will not line
    up, and nothing about the result looks like a font setting -- it looks like bad data."""
    source = read(LAYER / "EntryMapTypography.swift")
    steps = dict(
        (name, body)
        for name, body in re.findall(
            r"static let (\w+) = EntryMapTextStyle\((.*?)\)\n", source, re.S))
    assert len(steps) >= 10, "the type scale did not parse; this guard is pinning nothing"
    for name, body in steps.items():
        tabular = "tabularNumerals: true" in body
        expected = name.endswith("Numeric") or name == "display"
        assert tabular == expected, (
            f"{name} sets tabularNumerals: {tabular}; the naming says it should be {expected}")


def test_no_system_font_size_is_hardcoded_in_the_layer_or_the_restyled_screen():
    for swift in sorted(LAYER.glob("*.swift")) + screens():
        body = "\n".join(re.sub(r"//.*", "", line) for line in read(swift).splitlines())
        assert "Font.system(" not in body and ".font(.system(" not in body, (
            f"{swift.name} reaches past the scale to a system font")


def test_the_registered_fonts_are_the_faces_the_layer_asks_for():
    """A font registered under one name and asked for under another fails silently: iOS falls back
    to San Francisco and logs nothing the app can see."""
    asked = set(re.findall(r'return "([\w-]+\.ttf)"', read(LAYER / "EntryMapTypography.swift")))
    project = read(PROJECT)
    block = project.split("UIAppFonts:", 1)[1]
    registered = set(re.findall(r"-\s+([\w-]+\.ttf)", block.split("UISupported", 1)[0]))
    assert asked == registered, (
        f"asked for {sorted(asked)}, project.yml registers {sorted(registered)}")


# --------------------------------------------------------------------------- spacing


def test_spacing_and_radius_match_the_token_file():
    source = read(LAYER / "EntryMapLayout.swift")
    tokens = design_tokens()
    for step, value in tokens["spacing"].items():
        assert f"static let space{step}: CGFloat = {value}\n" in source, (
            f"spacing step {step} is not {value}")
    for name, value in tokens["radius"].items():
        swift = f"static let radius{name.capitalize()}: CGFloat = {value}\n"
        assert swift in source, f"radius {name} is not {value}"


def test_control_metrics_match_the_interaction_token():
    source = read(LAYER / "EntryMapLayout.swift")
    tokens = motion_tokens()["button"]
    assert f"touchTargetMinimum: CGFloat = {tokens['minimumTouchTargetPx']}" in source
    assert f"focusRingWidth: CGFloat = {tokens['focusRingPx']}" in source
    assert f"focusRingOffset: CGFloat = {tokens['focusOffsetPx']}" in source
    assert f"pressedScale: CGFloat = {tokens['pressedScale']}" in source
    stops = ", ".join(str(stop / 100) for stop in motion_tokens()["sheetStopsPercent"])
    assert f"sheetStops: [CGFloat] = [{stops}]" in source


# --------------------------------------------------------------------------- motion


def test_every_named_duration_matches_the_motion_token():
    source = read(LAYER / "EntryMapMotion.swift")
    block = source.split("var milliseconds: Int", 1)[1].split("var seconds", 1)[0]
    declared = dict(
        (name, int(value)) for name, value in re.findall(r"case \.(\w+): return (\d+)", block))
    tokens = motion_tokens()["durationMs"]
    # The scan is a process budget rather than a piece of motion, so it lives outside the ladder.
    budgets = {"scanTarget", "scanMaximum"}
    assert declared == {k: v for k, v in tokens.items() if k not in budgets}
    for name in budgets:
        seconds = tokens[name] / 1000
        assert f"{name}Duration: TimeInterval = {seconds:.3f}" in source, (
            f"{name} is not {seconds} s")


def test_every_easing_matches_the_motion_token():
    source = read(LAYER / "EntryMapMotion.swift")
    block = source.split("fileprivate var points", 1)[1].split("}", 1)[0]
    declared = {
        name: tuple(float(n) for n in numbers.split(", "))
        for name, numbers in re.findall(r"case \.(\w+): return \(([^)]+)\)", block)
    }
    for name, curve in motion_tokens()["easing"].items():
        expected = tuple(float(n) for n in re.findall(r"[\d.]+", curve))
        assert declared[name] == expected, f"{name} is {declared[name]}, token says {expected}"


def test_reduce_motion_stops_the_animation_rather_than_shortening_it():
    """The web build's mistake: every duration scaled down, every delay left alone. The fix is not
    a smaller number, it is no animation -- SwiftUI applies a nil animation instantly."""
    source = read(LAYER / "EntryMapMotion.swift")
    body = source.split("static func animation(", 1)[1].split("\n    }", 1)[0]
    assert "case .instant:\n                return nil" in body, (
        "the reduced path for moving elements must be nil, not a shorter duration")
    assert re.search(r"duration:\s*\w*\s*[*/]\s*\d", body) is None, (
        "a duration is being scaled somewhere in the reduced path")


def test_only_the_design_system_decides_what_reduce_motion_means():
    """Two screens each reading the setting is how it comes to mean two different things. A screen
    asks the layer for an animation; the layer is the only thing that reads the environment."""
    offenders = [
        swift.name
        for swift in (ROOT / "ios" / "FrontdoorCapture" / "UI").glob("*.swift")
        if "accessibilityReduceMotion" in read(swift)
    ]
    assert offenders == [], (
        f"{offenders} reads the Reduce Motion setting directly instead of asking EntryMapMotion")


def test_the_layer_produces_exactly_one_delay_and_it_cannot_gate_visibility():
    """A delay that decides when something exists is what broke focus into every sheet."""
    delaying = {
        swift.name for swift in LAYER.glob("*.swift")
        if ".delay(" in re.sub(r"//.*", "", read(swift))
    }
    assert delaying == set(), f"a delay appeared in {sorted(delaying)}"
    stagger = read(LAYER / "EntryMapMotion.swift").split("static func stagger(", 1)[1]
    assert "guard !reduceMotion, index > 0 else { return 0 }" in stagger, (
        "the stagger must collapse to zero under Reduce Motion")


def test_the_button_uses_the_named_press_and_release_timings():
    source = read(LAYER / "EntryMapButtonStyle.swift")
    assert "EntryMapMotion.animation(.press" in source
    assert "EntryMapMotion.releaseAnimation(" in source
    assert "EntryMapMotion.animation(.focus" in source


# --------------------------------------------------------------------------- pins


def test_pin_sizes_match_the_hierarchy_token():
    source = read(LAYER / "EntryMapPin.swift")
    block = source.split("func size(for tier: EntryMapTrustTier)", 1)[1].split(
        "\n    }", 1)[0]
    sizes = pin_tokens()["sizes"]
    contexts = {
        "overview": "overviewPx", "street": "streetPx",
        "selected": "selectedPx", "receipt": "receiptPx",
    }
    for context, key in contexts.items():
        # Context cases sit at eight spaces; the tier cases inside them at twelve.
        outer = "\n        case ."
        section = block.split(f"{outer}{context}:", 1)[1].split(outer, 1)[0]
        declared = dict(
            (tier, int(value)) for tier, value in re.findall(r"case \.(\w+): return (\d+)", section))
        assert declared == sizes[key], f"{context} sizes are {declared}, token says {sizes[key]}"
    assert f"case .liveScanDrop:\n            return {sizes['liveScanDropPx']}" in block
    assert f"clusterSize: CGFloat = {sizes['clusterPx']}" in source


def test_render_order_matches_the_hierarchy_token():
    source = read(LAYER / "EntryMapPin.swift")
    block = source.split("enum ZIndex {", 1)[1].split("\n    }", 1)[0]
    declared = dict(
        (name, int(float(value)))
        for name, value in re.findall(r"static let (\w+): Double = ([\d.]+)", block))
    expected = dict(pin_tokens()["sizes"]["zIndex"])
    # The two token files name level 50 differently; the number and its place are what matter.
    expected["needsMatch"] = expected.pop("matched")
    assert declared == expected


def test_no_tier_is_told_by_colour_alone():
    """A greyscale projector, a colour-blind reader and a screenshot all have to work."""
    source = read(LAYER / "EntryMapPin.swift")
    rings = dict(
        (tier, int(count)) for tier, count in re.findall(
            r"case \.(\w+): return (\d)\n",
            source.split("var filledRings: Int", 1)[1].split("\n    }", 1)[0]))
    assert rings == {"estimated": 0, "scannedOnSite": 2, "ownerConfirmed": 3}
    symbols = source.split("private var tierSymbol", 1)[1]
    for tier in ("estimated", "scannedOnSite", "ownerConfirmed"):
        assert f"case .{tier}:" in symbols, f"{tier} has no symbol of its own"
        assert f'case .{tier}: return "' in source, f"{tier} has no spoken label"


def test_an_overlay_never_recolours_a_pin():
    """Selection, matching and freshness may add to a pin. None of them may restate its tier."""
    source = read(LAYER / "EntryMapPin.swift")
    selection = source.split("if isSelected {", 1)[1].split("}", 1)[0]
    for tier_colour in ("sky400", "marigold400", "violet600"):
        assert tier_colour not in selection, (
            f"the selection overlay paints {tier_colour}, which is a tier colour")


def test_the_pin_body_is_the_masters_own_path():
    source = read(LAYER / "EntryMapPin.swift")
    literal = source.split("private static let bodyCommands =", 1)[1].split('Z"', 1)[0] + 'Z"'
    declared = "".join(re.findall(r'"([^"]*)"', literal))
    # Without this the guard is worse than useless: an unparsed literal leaves `declared` empty,
    # and the empty string is a substring of every file, so it would pass against anything.
    assert len(declared) > 100, "bodyCommands did not parse; this guard is pinning nothing"
    masters = sorted((SVG / "pins").glob("*.svg"))
    assert len(masters) == 3, f"expected three pin masters, found {len(masters)}"
    for master in masters:
        assert declared in read(master), (
            f"the pin body no longer matches {master.name}")


# --------------------------------------------------------------------------- icons


SVG_ELEMENT = re.compile(r"<(path|circle|rect)\b([^>]*)>")
SVG_ATTR = re.compile(r'(\w[\w-]*)="([^"]*)"')


def glyphs_in_master(relative_path):
    """Every drawable element of an SVG master, in document order, as comparable tuples."""
    text = read(SVG / f"{relative_path}.svg")
    out = []
    for tag, attributes in SVG_ELEMENT.findall(text):
        a = dict(SVG_ATTR.findall(attributes))
        if tag == "path":
            out.append(("path", a["d"]))
        elif tag == "circle":
            out.append(("circle", float(a["cx"]), float(a["cy"]), float(a["r"])))
        else:
            out.append((
                "rect", float(a["x"]), float(a["y"]),
                float(a["width"]), float(a["height"]), float(a.get("rx", 0))))
    return out


def glyphs_in_swift():
    """Every icon's glyph list, read out of `EntryMapIcon.glyphs`."""
    source = read(LAYER / "EntryMapIcons.swift")
    raws = dict(re.findall(r'case (\w+) = "([\w/-]+)"', source))
    block = source.split("var glyphs: [EntryMapGlyph] {", 1)[1]
    out = {}
    for case, body in re.findall(r"case \.(\w+):\n(.*?)(?=\n        case \.|\n        \}\n)",
                                 block, re.S):
        glyphs = []
        for kind, arguments in re.findall(r"\.(path|circle|rect)\((.*)\)", body):
            if kind == "path":
                glyphs.append(("path", re.match(r'"(.*?)"', arguments).group(1)))
            else:
                numbers = [float(n) for n in re.findall(r"-?[\d.]+", arguments)]
                # `dash:` is styling, not geometry -- circle takes three numbers, rect five.
                glyphs.append((kind, *numbers[:3 if kind == "circle" else 5]))
        out[raws[case]] = glyphs
    return out


def test_every_icon_is_the_approved_master_and_not_a_redrawing():
    swift = glyphs_in_swift()
    assert len(swift) == 28, f"expected 28 icons, read {len(swift)}"
    for relative_path, glyphs in swift.items():
        assert glyphs == glyphs_in_master(relative_path), (
            f"{relative_path} has been redrawn by hand")


def test_every_icon_case_has_a_master_committed_beside_it():
    source = read(LAYER / "EntryMapIcons.swift")
    cases = re.findall(r'case (\w+) = "([\w/-]+)"', source)
    assert len(cases) == 28, f"expected 28 icon cases, read {len(cases)}"
    for _, relative_path in cases:
        assert (SVG / f"{relative_path}.svg").exists(), f"no master for {relative_path}"


SUPPORTED_COMMANDS = set("MLHVCSAZmlhvcsaz")


def test_the_masters_only_use_path_commands_the_parser_supports():
    """The parser draws nothing at all for a command it does not know, which is loud. This says so
    before anybody sees an empty icon."""
    for master in sorted(SVG.rglob("*.svg")):
        for data in re.findall(r'\sd="([^"]+)"', read(master)):
            used = set(re.findall(r"[A-Za-z]", data))
            assert used <= SUPPORTED_COMMANDS, (
                f"{master.name} uses {sorted(used - SUPPORTED_COMMANDS)}, which "
                "EntryMapPathParser does not implement")


# --------------------------------------------------------------------------- controls


def test_the_unavailable_control_is_lavender_and_indigo_and_never_grey():
    source = read(LAYER / "EntryMapButtonStyle.swift")
    body = "\n".join(re.sub(r"//.*", "", line) for line in source.splitlines())
    assert "if isUnavailable { return EntryMapPalette.lavender200 }" in body
    assert "if isUnavailable { return EntryMapPalette.ink }" in body
    for grey in (".gray", "grey", "systemGray", "foregroundStyle(.secondary"):
        assert grey not in body, f"the control layer reaches for {grey}"


def test_an_unavailable_control_still_receives_the_tap():
    """The spec says tapping an unavailable control explains what is needed. A SwiftUI button that
    is `.disabled` never hears the tap, so the explanation never happens."""
    body = "\n".join(
        re.sub(r"//.*", "", line)
        for line in read(LAYER / "EntryMapButtonStyle.swift").splitlines())
    assert ".disabled(" not in body
    assert "unavailableExplanation" in body


def test_the_scan_control_is_the_only_one_with_a_medium_haptic():
    source = read(LAYER / "EntryMapButtonStyle.swift")
    assert "role == .scan ? .medium : .light" in source


# --------------------------------------------------------------------------- brand


def test_the_brand_mark_is_the_approved_artwork():
    imageset = (ROOT / "ios" / "FrontdoorCapture" / "Resources" / "Assets.xcassets"
                / "EntryMapLogo.imageset")
    contents = json.loads(read(imageset / "Contents.json"))
    scales = {image["scale"] for image in contents["images"]}
    assert scales == {"1x", "2x", "3x"}
    for image in contents["images"]:
        assert (imageset / image["filename"]).exists()
    assert (ROOT / "docs" / "brand" / "entrymap-approved-logo.png").exists()


def test_the_libraries_degraded_mark_is_not_in_the_repository():
    """It drops the white disc and strokes the middle arc in the pin's own violet, so it shows one
    arc where the logo has three. It looks like a logo in a folder listing, which is the problem."""
    strays = [path for path in ROOT.rglob("mark-primary.*") if ".venv" not in str(path)]
    assert strays == [], f"the degraded reproduction is committed at {strays}"


# --------------------------------------------------------------------------- the worked example


# A system menu is drawn by UIKit from a title and an SF Symbol, not from a SwiftUI view, so
# `EntryMapIconView` cannot appear in one. The viewfinder's view-picker is the only menu in the
# app and the only place a symbol name is allowed to survive.
SYMBOL_EXEMPT = {"CaptureView.swift"}


def test_no_screen_names_a_style_of_its_own():
    """The point of the layer is that a screen cannot be styled by eye.

    Before #367 exactly one screen went through the tokens and eleven were on SwiftUI defaults --
    which meant the design system was a folder, not a rule. This is the rule.
    """
    offenders = {}
    for swift in screens():
        body = "\n".join(re.sub(r"//.*", "", line) for line in read(swift).splitlines())
        reaches = [".font(", "Color(", ".foregroundStyle(.secondary)",
                   ".foregroundStyle(.primary)", ".buttonStyle(.bordered",
                   ".buttonStyle(.borderedProminent)", "monospacedDigit",
                   ".thinMaterial", ".regularMaterial", ".quaternary"]
        if swift.name not in SYMBOL_EXEMPT:
            reaches += ["systemImage:", "Image(systemName:"]
        found = [reach for reach in reaches if reach in body]
        if found:
            offenders[swift.name] = found
    assert offenders == {}, f"screens styling themselves instead of using the tokens: {offenders}"


def test_no_screen_spells_a_colour_swiftui_supplies():
    """`.green` for present and `.red` for absent is the failure this catches.

    The palette has no red and no green, and that is not an oversight -- the map's own rule is
    that colour never carries a verdict about a business, and a screen that paints one is making
    a claim the product refuses to make. It is also the pairing colour-blind readers cannot tell
    apart, on the screen that delivers the finding.
    """
    named = re.compile(
        r"(?:Color|foregroundStyle|background|tint|fill|stroke|strokeBorder)"
        r"[(.]\s*\.?(?:black|white|red|green|blue|orange|yellow|gray|grey|purple|pink|brown"
        r"|mint|teal|cyan|indigo|accentColor)\b")
    offenders = {}
    for swift in screens():
        body = "\n".join(re.sub(r"//.*", "", line) for line in read(swift).splitlines())
        found = named.findall(body)
        if found:
            offenders[swift.name] = found
    assert offenders == {}, f"SwiftUI's own colours used instead of the palette: {offenders}"


def test_every_screen_actually_reaches_the_tokens():
    """The inverse of the guard above: a screen can pass it by being blank.

    Every screen in the app draws something, so every screen names the palette and the scale.
    """
    offenders = [
        swift.name for swift in screens()
        if not ("EntryMapPalette." in read(swift) and "EntryMapTypography." in read(swift))
    ]
    # RootView draws no content of its own -- it is the router between the screens that do.
    assert offenders == ["RootView.swift"], (
        f"screens that never reach the design system: {offenders}")


# --------------------------------------------------------------------------- the build itself


def test_the_asset_catalog_does_not_silently_require_an_app_icon():
    """A catalog with no AppIcon set fails the build, and CI never builds Swift.

    The design-system port added Resources/Assets.xcassets. The moment a catalog exists, Xcode
    looks for the icon set named by ASSETCATALOG_COMPILER_APPICON_NAME -- default "AppIcon" -- and
    fails when it is absent. `main` could not build an iOS app for some hours because of it, and
    nothing in the Python suite could see that.

    So either the catalog carries an AppIcon set, or the project says there is no app icon. What
    is not allowed is the state in between.
    """
    project = (ROOT / "ios" / "project.yml").read_text(encoding="utf-8")
    catalog = ROOT / "ios" / "FrontdoorCapture" / "Resources" / "Assets.xcassets"
    if not catalog.is_dir():
        return
    has_icon_set = any(child.name.endswith(".appiconset") for child in catalog.iterdir())
    declares_none = 'ASSETCATALOG_COMPILER_APPICON_NAME: ""' in project
    assert has_icon_set or declares_none, (
        "Assets.xcassets exists with no AppIcon set and project.yml does not say the app has no "
        "icon, so xcodebuild fails. Add an AppIcon.appiconset or set "
        'ASSETCATALOG_COMPILER_APPICON_NAME: "".'
    )
