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


def palette_colours():
    return {name: value.lstrip("#").upper() for name, value in design_tokens()["color"].items()}


ROLE_DECLARATION = re.compile(r"((?:^[ ]*///.*\n)*)^[ ]*static let (\w+) = (\w+)$", re.M)


def palette_roles():
    """`{role: the token or role it is}`, read off `static let <role> = <name>`."""
    source = read(LAYER / "EntryMapPalette.swift")
    return {match.group(2): match.group(3) for match in ROLE_DECLARATION.finditer(source)}


def resolve(name):
    """A role or token name, followed to the hex the token file gives it."""
    colours, roles = palette_colours(), palette_roles()
    seen = set()
    while name not in colours:
        assert name in roles and name not in seen, f"{name} is neither a token nor a role"
        seen.add(name)
        name = roles[name]
    return colours[name]


def test_the_palette_is_the_official_colours_and_nothing_else():
    source = read(LAYER / "EntryMapPalette.swift")
    declared = dict(
        re.findall(r"static let (\w+) = Color\(entryMapHex: 0x([0-9A-F]{6})\)", source))
    official = palette_colours()
    assert len(official) >= 11, "the token file's colour block did not parse"
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
        # `\bColor\(` so `UIColor(EntryMapPalette.ink)` is not read as a raw colour -- converting
        # an approved token for UIKit is the opposite of spelling one. `UIColor(` on anything else
        # is still caught, which is what stops that becoming the loophole.
        # `UIColor\.` catches the dot-syntax form. `UIColor(EntryMapPalette.ink)` is a paren and
        # so is not matched by it -- converting an approved token for UIKit is the opposite of
        # spelling a colour, and is the only UIColor this layer is allowed.
        found = re.findall(
            r"\bColor\(|UIColor\((?!EntryMapPalette\.)|UIColor\.|"
            r"0x[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{6}\b",
            body)
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


# ------------------------------------------------- the canonical palette and its stated figures
#
# The library's `2026-09-05` version moved ten of the eleven colours it had previously named --
# every one except white -- and added `lavenderPath`. Nothing measured against the retired set
# carries over, and the tests below are what stops a figure from outliving the colour it described.

RETIRED_COLOURS = {
    "indigo900": "17103D",
    "indigo800": "211054",
    "violet600": "5B35F5",
    "violet800": "4020B5",
    "sky400": "69B7FF",
    "sky700": "1266A6",
    "marigold400": "FFBF24",
    "amber700": "9A5700",
    "lavender100": "F2EEFF",
    "lavender200": "E2DAFF",
}

FIGURE = re.compile(r"\d+\.\d+:1")
EXPLICIT_FIGURE = re.compile(r"(\d+\.\d+):1 `(\w+)` on `(\w+)`")
ROLE_FIGURE = re.compile(r"(\d+\.\d+):1 on `(\w+)`")


def layer_sources():
    return sorted(LAYER.glob("*.swift")) + [PRIMER]


def stated_figures():
    """Every contrast figure written in the layer, and every one written unparseably.

    Two forms are allowed. ``R:1 `foreground` on `background``` states both sides; ``R:1 on
    `background```, inside a role's own documentation, takes its foreground from the role being
    documented. A figure that is deliberately historical carries the word "retired" on its line.

    Anything else lands in the second list and fails, because a figure nothing can recompute is
    exactly what survived the last palette change.
    """
    figures, unparsed = [], []
    for swift in layer_sources():
        source = read(swift)
        documented = {}
        for match in ROLE_DECLARATION.finditer(source):
            if not match.group(1):
                continue
            first = source[:match.start(1)].count("\n")
            for offset in range(match.group(1).count("\n")):
                documented[first + offset] = match.group(2)
        for number, line in enumerate(source.splitlines()):
            for figure in FIGURE.finditer(line):
                explicit = EXPLICIT_FIGURE.match(line, figure.start())
                short = ROLE_FIGURE.match(line, figure.start())
                if explicit:
                    figures.append((swift.name, number + 1, explicit.group(2), explicit.group(3),
                                    float(explicit.group(1))))
                elif short and number in documented:
                    figures.append((swift.name, number + 1, documented[number], short.group(2),
                                    float(short.group(1))))
                elif "retired" not in line:
                    unparsed.append(f"{swift.name}:{number + 1}: {line.strip()}")
    return figures, unparsed


def test_every_contrast_figure_in_the_layer_is_recomputed_from_the_token_file():
    """The layer's old figures were measured against colours that no longer exist. Ten of eleven
    moved, so every one of them was wrong and none of them looked wrong."""
    figures, unparsed = stated_figures()
    assert unparsed == [], (
        "these figures are not in a form this guard can recompute, and an unchecked figure is how "
        f"the retired numbers survived the last palette change: {unparsed}")
    assert len(figures) >= 12, (
        f"only {len(figures)} figures parsed out of the layer; this guard is pinning nothing")
    for name, line, foreground, background, stated in figures:
        actual = wcag_ratio(resolve(foreground), resolve(background))
        assert abs(actual - stated) < 0.02, (
            f"{name}:{line} says {foreground} on {background} is {stated}:1; against the token "
            f"file it is {actual:.2f}:1")


def test_the_figures_the_packages_report_also_states_agree_with_it():
    """Recomputing is not enough on its own: an arithmetically true figure for a pairing the
    library approves must also be the figure the library published for it."""
    approved = approved_pairings()
    figures, _ = stated_figures()
    checked = 0
    for name, line, foreground, background, stated in figures:
        pair = (resolve(foreground), resolve(background))
        published = approved.get(pair, approved.get((pair[1], pair[0])))
        if published is None:
            continue
        checked += 1
        # Exactly, not approximately: the layer is restating the report's own published number.
        assert published == stated, (
            f"{name}:{line} states {stated}:1 where the report publishes {published}:1")
    assert checked >= 6, (
        f"only {checked} of the layer's figures matched a report row; the report did not parse")


def test_body_copy_clears_the_packages_seven_to_one_floor():
    """The package sets a 7:1 floor for body copy. The pairing that could not meet it was white on
    the violet; the canonical violet is what lifts it."""
    assert "at least 7:1" in read(TOKENS / "contrast-report.md"), (
        "the contrast report no longer states a body floor")
    body = [
        ("ink", "card"), ("ink", "ground"), ("subduedInk", "card"),
        ("onDarkGround", "darkGround"), ("onViolet", "violet600"), ("onMarigold", "marigold400"),
    ]
    for foreground, background in body:
        actual = wcag_ratio(resolve(foreground), resolve(background))
        assert actual >= 7, (
            f"{foreground} on {background} is {actual:.2f}:1, under the package's 7:1 body floor")
    # The two accents that do not clear it are not body roles, and each says so where it is defined.
    source = read(LAYER / "EntryMapPalette.swift")
    for accent in ("freshness", "informationInk"):
        assert wcag_ratio(resolve(accent), resolve("card")) < 7, (
            f"{accent} now clears the floor; its documentation calls it a non-body colour")
        assert accent not in [role for role, _ in body], f"{accent} is being used as body copy"
        block = source.split(f"static let {accent} = ")[0].rsplit("\n\n", 1)[-1]
        assert "body floor" in block, (
            f"{accent} is under the 7:1 floor and its documentation does not say so")


def test_the_pin_paths_lavender_is_a_role_of_its_own_and_never_paints_a_surface():
    """The web build spent one lavender family on the pin path and on its surfaces, and every
    screen came out with a purple cast and white slots cut into it. The separation is the fix."""
    colours, roles = palette_colours(), palette_roles()
    assert "lavenderPath" in colours, "the token file no longer carries the pin path's lavender"
    assert colours["lavenderPath"] not in (colours["lavender100"], colours["lavender200"]), (
        "the pin path and the UI lavenders are one value again")
    assert roles.get("pathLine") == "lavenderPath", "no named role spends the pin path's lavender"
    for surface in ("ground", "card", "darkGround", "edge"):
        assert resolve(surface) != colours["lavenderPath"], (
            f"the {surface} role paints the pin path's lavender; that is the purple cast, rebuilt")
    painting, calls = [], []
    for swift in layer_sources():
        if swift.name == "EntryMapPalette.swift":
            continue
        body = "\n".join(re.sub(r"//.*", "", line) for line in read(swift).splitlines())
        found = re.findall(r"\.(?:background|fill|strokeBorder|foregroundStyle)\([^\n]*", body)
        calls += found
        painting += [f"{swift.name}: {call.strip()}" for call in found
                     if "pathLine" in call or "lavenderPath" in call]
        if "lavenderPath" in body:
            painting.append(f"{swift.name} reaches past the role to the raw token")
    assert len(calls) >= 10, "no paint calls parsed out of the layer; this guard is scanning nothing"
    assert painting == [], f"the pin path's lavender is being painted onto a surface: {painting}"


def test_the_deeper_steps_are_named_roles_rather_than_token_names_at_the_call_site():
    """The second indigo, the second violet, the deeper sky and the muted amber.

    `indigo800` is the exception and is meant to be: the library declares it and then draws nothing
    with it -- it is in no piece of artwork, no control state and no row of the contrast report --
    so the palette names no role for it rather than inventing a use.
    """
    palette = read(LAYER / "EntryMapPalette.swift")
    steps = ("indigo800", "violet800", "sky700", "amber700")
    for step in steps:
        assert f"static let {step} = Color(entryMapHex:" in palette, f"{step} is not declared"
    spent = palette_roles().values()
    for step in ("violet800", "sky700", "amber700"):
        assert step in spent, f"no role in the palette spends {step}"
    sources = layer_sources()
    assert len(sources) >= 10, "the layer did not glob; this guard is scanning nothing"
    offenders = {}
    for swift in sources:
        if swift.name == "EntryMapPalette.swift":
            continue
        body = "\n".join(re.sub(r"//.*", "", line) for line in read(swift).splitlines())
        found = [step for step in steps if step in body]
        if found:
            offenders[swift.name] = found
    assert offenders == {}, (
        f"a deeper step is spelled at the call site instead of through a role: {offenders}")


def test_no_retired_palette_value_survives_in_the_layer_or_the_copied_library():
    """`docs/design/entrymap/README.md` records the retired values on purpose -- it is the note
    saying what this copy replaced. Everywhere else they are colours nobody approves any more."""
    scanned = layer_sources() + [
        path for path in sorted(TOKENS.rglob("*"))
        if path.is_file() and path.name != "README.md"
    ]
    assert len(scanned) > 40, f"only {len(scanned)} files scanned; this guard is pinning nothing"
    haystack = {path: read(path).upper() for path in scanned}
    current = palette_colours()
    for name, retired in RETIRED_COLOURS.items():
        assert current[name] != retired, f"{name} is still the retired #{retired}"
        strays = sorted({path.name for path, text in haystack.items() if retired in text})
        assert strays == [], f"the retired {name} #{retired} is still spelled in {strays}"
    # If the search could not find a colour that is definitely there, the loop above proves nothing.
    for name, value in current.items():
        assert any(value in text for text in haystack.values()), (
            f"the canonical {name} #{value} is in none of the files this guard searches")


def test_the_copied_library_says_which_version_it_is_and_what_it_replaced():
    """This directory is replaced wholesale when the library issues a version. A copy that does not
    say which version it is cannot be checked against anything."""
    readme = read(TOKENS / "README.md")
    assert re.search(r"version `\d{4}-\d{2}-\d{2}`", readme), (
        "the copy does not record which library version it is")
    current = palette_colours()
    for name, retired in RETIRED_COLOURS.items():
        assert f"`#{retired}`" in readme, f"the copy does not say {name} replaced #{retired}"
        assert f"`#{current[name]}`" in readme, f"the copy does not say what {name} is now"
    assert f"`#{current['lavenderPath']}`" in readme, (
        "the copy does not name the role the library added")


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


def _postscript_name(path):
    """The name `UIFont(name:)` and `Font.custom(_:)` actually resolve, read out of the file.

    Not the filename and not the family: three different names, and only this one decides
    whether the app renders in its own typeface or silently in San Francisco.
    """
    import struct

    data = path.read_bytes()
    tables = struct.unpack(">H", data[4:6])[0]
    offset = None
    for index in range(tables):
        entry = 12 + 16 * index
        if data[entry:entry + 4] == b"name":
            offset = struct.unpack(">I", data[entry + 8:entry + 12])[0]
    assert offset is not None, f"{path.name} has no name table"
    count, storage = struct.unpack(">HH", data[offset + 2:offset + 6])
    for index in range(count):
        record = offset + 6 + 12 * index
        platform, _, _, name_id, length, string_offset = struct.unpack(
            ">HHHHHH", data[record:record + 12])
        if name_id != 6:
            continue
        raw = data[offset + storage + string_offset:][:length]
        return raw.decode("utf-16-be") if platform == 3 else raw.decode("latin-1")
    return None


def test_every_face_the_layer_names_is_present_and_resolvable():
    """The check that could not exist until the files did.

    Before this, `Resources/Fonts` held a README and nothing else, and the app rendered in
    San Francisco at the scale's sizes and weights with nothing in the log to say so. The
    guard that was supposed to cover it compared the .ttf names Swift asks for against the
    UIAppFonts list -- two lists that were both satisfied by files nobody had added.

    A missing file is caught here. So is the subtler one: a face whose PostScript name does
    not match the raw value, which is what `Font.custom` resolves and what no filename check
    can see.
    """
    directory = ROOT / "ios" / "FrontdoorCapture" / "Resources" / "Fonts"
    faces = dict(re.findall(
        r'case (\w+) = "([\w-]+)"', read(LAYER / "EntryMapTypography.swift")))
    files = dict(re.findall(
        r'case \.(\w+): return "([\w-]+\.ttf)"', read(LAYER / "EntryMapTypography.swift")))
    assert faces and files, "could not read the Face enum"

    missing, mismatched = [], []
    for case, postscript in faces.items():
        path = directory / files[case]
        if not path.exists():
            missing.append(files[case])
            continue
        actual = _postscript_name(path)
        if actual != postscript:
            mismatched.append(f"{files[case]} is {actual!r}, Swift asks for {postscript!r}")
    assert not missing, (
        f"faces the layer names but the bundle does not carry: {missing}. "
        "The app renders in San Francisco and says nothing.")
    assert not mismatched, f"PostScript names that will not resolve: {mismatched}"


def test_the_font_licences_travel_with_the_fonts():
    """Both families are OFL, which requires the licence to be distributed with them."""
    directory = ROOT / "ios" / "FrontdoorCapture" / "Resources" / "Fonts"
    licences = sorted(p.name for p in directory.glob("OFL*.txt"))
    assert licences == ["OFL-AtkinsonHyperlegibleNext.txt", "OFL-NunitoSans.txt"], licences
    for name in licences:
        assert "SIL OPEN FONT LICENSE" in read(directory / name).upper()


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
    # `readsAsUnavailable`, not `isUnavailable`: the paint now covers a control that was told it
    # is unavailable AND one that simply cannot act. The colours it lands on are unchanged, which
    # is what this test is about.
    assert "if readsAsUnavailable { return EntryMapPalette.lavender200 }" in body
    assert "if readsAsUnavailable { return EntryMapPalette.ink }" in body
    for grey in (".gray", "grey", "systemGray", "foregroundStyle(.secondary"):
        assert grey not in body, f"the control layer reaches for {grey}"


def test_a_disabled_control_is_painted_unavailable_rather_than_ready():
    """`.disabled(_:)` over this style used to change nothing an eye could see.

    The control kept its full violet fill and stopped answering, so "ready" and "cannot act"
    looked identical -- found on the ROI footer's "Use frame", sitting at full saturation with
    nothing marked yet. Five screens apply `.disabled(_:)` over the style, so the style is where
    this has to be answered; a screen-by-screen fix would be five chances to forget.

    This is a floor, not the intent. The intent is the test below: an unavailable control keeps
    the tap and says what is needed.
    """
    body = read(LAYER / "EntryMapButtonStyle.swift")
    assert "@Environment(\\.isEnabled)" in body, (
        "the style never reads isEnabled, so a disabled control paints as a ready one")
    assert "isUnavailable || !isEnabled" in body, (
        "the unavailable paint must cover both the flag and a disabled control")
    # Every paint decision goes through the combined test, never the flag alone.
    stripped = "\n".join(re.sub(r"//.*", "", line) for line in body.splitlines())
    assert "if isUnavailable" not in stripped, (
        "a paint branch still reads the flag alone, so a disabled control slips past it")


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


def test_no_screen_takes_a_system_control_style():
    """A grey segmented control in the middle of a restyled screen is what this catches.

    The screens passed every other guard here while `Picker(...).pickerStyle(.segmented)` sat on
    the home screen in the system font and the system greys, because the guards look for styling a
    screen *writes* and a system control style is a request for styling nobody wrote. Any control
    style the design system has no token for is the same bug waiting to happen.
    """
    # An allow-list, because the denylist this replaced promised the class and delivered nine
    # strings: `.pickerStyle(SegmentedPickerStyle())` -- the same defect in the older spelling --
    # and `.textFieldStyle(.roundedBorder)` both walked straight through it.
    #
    # `foregroundStyle` is not a control style; the palette guards below own it.
    control_style = re.compile(r"\.(?!foregroundStyle)(\w+Style)\(\s*([^\n]*)")
    allowed = ("EntryMapButtonStyle(", ".plain)")
    offenders = {}
    for swift in screens():
        body = "\n".join(re.sub(r"//.*", "", line) for line in read(swift).splitlines())
        found = [f".{name}({arg.strip()[:40]}" for name, arg in control_style.findall(body)
                 if not arg.lstrip().startswith(allowed)]
        if found:
            offenders[swift.name] = found
    assert offenders == {}, (
        f"screens taking a control style the design system has no token for: {offenders}. "
        "Use EntryMapButtonStyle, or .plain to say the screen draws its own chrome.")


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
