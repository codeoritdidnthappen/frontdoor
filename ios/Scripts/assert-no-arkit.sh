#!/bin/sh
# D-015: the method may consume one RGB still, intrinsics and gravity — nothing motion-derived.
# ARKit's visual-inertial odometry recovers metric scale from motion, which would make the research
# question uninteresting. The boundary is enforced by construction: if no AR session is ever
# started, motion-derived scale is not merely forbidden, it is unavailable.
#
# THIS SCRIPT IS THE ONLY IMPLEMENTATION OF THE RULE. tests/test_ios_no_arkit.py invokes it rather
# than reimplementing it, so the Xcode guard and the CI guard cannot drift apart (#151, #154). It is
# POSIX sh and plain grep, so it runs on a Linux CI runner with no Xcode.
#
# Matches code, not prose. Comments are stripped before matching, because a guard that fails the
# build on a comment explaining the boundary is a guard someone deletes (#152).
set -eu
ROOT="${1:?usage: assert-no-arkit.sh <ios-dir>}"

# Any attribute, with or without arguments, before an import: @testable, @_exported,
# @preconcurrency, @_spi(Internal), @_documentation(visibility: internal) (#153).
IMPORTS='^[[:space:]]*(@[_A-Za-z][_A-Za-z0-9]*(\([^)]*\))?[[:space:]]+)*import[[:space:]]+(ARKit|RealityKit)([[:space:].]|$)'
# The AR namespace, not a hand-listed set of seven types (#148). ARKit's public types are AR
# followed by a capital and containing at least one lowercase letter: ARSession, ARFrame,
# ARGeoTrackingConfiguration, ARMeshAnchor, ARSCNView. Requiring the lowercase is what keeps
# SHOUTING words like ARCHITECTURE — which appears in our own prose and filenames — from matching.
SYMBOLS='\b(AR[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*|RealityKit)\b'
status=0

# Strips /* */ blocks and // line comments. Over-stripping is safe here: anything inside a comment
# is not code, and a real import never shares a line with a trailing comment marker.
strip_comments() {
    awk '
        { line = $0; out = ""
          while (length(line) > 0) {
              if (in_block) {
                  i = index(line, "*/")
                  if (i == 0) { line = ""; break }
                  in_block = 0; line = substr(line, i + 2); continue
              }
              b = index(line, "/*"); l = index(line, "//")
              if (l > 0 && (b == 0 || l < b)) { out = out substr(line, 1, l - 1); line = ""; break }
              if (b > 0) { out = out substr(line, 1, b - 1); line = substr(line, b + 2); in_block = 1; continue }
              out = out line; line = ""
          }
          print out
        }' "$1"
}

# NUL-delimited, because word-splitting $(find ...) silently skips any path containing a space --
# and a skipped file is an unscanned file, which is a bypass of the only implementation of D-015.
scanned=0
while IFS= read -r f; do
    [ -n "$f" ] || continue
    if [ ! -r "$f" ]; then
        echo "error: cannot read $f; refusing to report a pass over a file that was not scanned." >&2
        status=1
        continue
    fi
    scanned=$((scanned + 1))
    hits=$(strip_comments "$f" | grep -nE "$IMPORTS|$SYMBOLS" || true)
    if [ -n "$hits" ]; then
        if [ "$status" -eq 0 ]; then
            echo "error: ARKit reached the capture app sources. D-015 forbids it; see ARCHITECTURE.md section 2." >&2
        fi
        echo "$hits" | sed "s|^|error: $f:|" >&2
        status=1
    fi
done <<EOF
$(find "$ROOT" -name '*.swift' -type f 2>/dev/null)
EOF

# A dependency line links the framework even with no import anywhere.
if [ -f "$ROOT/project.yml" ]; then
    if deps=$(grep -nE "^[[:space:]]*-[[:space:]]*sdk:.*\b(ARKit|RealityKit)\b" "$ROOT/project.yml" 2>/dev/null); then
        echo "error: an ARKit framework is linked in project.yml. D-015 forbids it." >&2
        echo "$deps" | sed 's/^/error: /' >&2
        status=1
    fi
fi

# Zero files scanned is a failure, not a pass. A renamed or moved tree would otherwise report
# success over nothing, and D-015 would be unenforced with a green check -- the same silent-pass
# class as the space-in-path bypass this loop was rewritten to close.
if [ "$scanned" -eq 0 ]; then
    echo "error: no Swift sources found under $ROOT. Refusing to report a pass over nothing." >&2
    status=1
fi

[ "$status" -eq 0 ] && echo "no-arkit check passed: $ROOT ($scanned swift files scanned)"
exit "$status"
