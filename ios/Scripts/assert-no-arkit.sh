#!/bin/sh
# D-015: the method may consume one RGB still, intrinsics and gravity — nothing motion-derived.
# ARKit's visual-inertial odometry recovers metric scale from motion, which would make the
# research question uninteresting. The boundary is enforced by construction: if no AR session is
# ever started, motion-derived scale is not merely forbidden, it is unavailable.
#
# Scans two things, because importing ARKit is not the only way to link it:
#   - Swift sources, for imports and symbol use
#   - project.yml, for an ARKit framework dependency with no corresponding import
#
# Runs as an Xcode pre-build phase. The same rule is asserted from CI by
# tests/test_ios_no_arkit.py, so it holds on a Linux runner with no Xcode.
set -eu
ROOT="${1:?usage: assert-no-arkit.sh <ios-dir>}"
PATTERN='\b(ARKit|ARSession|ARConfiguration|RealityKit)\b'
status=0

if hits=$(grep -rnE "$PATTERN" "$ROOT" --include='*.swift' 2>/dev/null); then
    echo "error: ARKit reached the capture app sources. D-015 forbids it; see ARCHITECTURE.md section 2." >&2
    echo "$hits" | sed 's/^/error: /' >&2
    status=1
fi

# A dependency line links the framework even with no import anywhere.
if [ -f "$ROOT/project.yml" ]; then
    if deps=$(grep -nE "^[[:space:]]*-[[:space:]]*sdk:.*$PATTERN" "$ROOT/project.yml" 2>/dev/null); then
        echo "error: an ARKit framework is linked in project.yml. D-015 forbids it." >&2
        echo "$deps" | sed 's/^/error: /' >&2
        status=1
    fi
fi

[ "$status" -eq 0 ] && echo "no-arkit check passed: $ROOT"
exit "$status"
