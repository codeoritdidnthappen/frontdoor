#!/bin/sh
# D-015: the method may consume one RGB still, intrinsics and gravity — nothing motion-derived.
# ARKit's visual-inertial odometry recovers metric scale from motion, which would make the
# research question uninteresting. The boundary is enforced by construction: if no AR session is
# ever started, motion-derived scale is not merely forbidden, it is unavailable.
#
# This runs as an Xcode pre-build phase. The same rule is asserted from CI by
# tests/test_ios_no_arkit.py, so it holds on a Linux runner with no Xcode.
set -eu
SOURCES="${1:?usage: assert-no-arkit.sh <sources-dir>}"

if hits=$(grep -rnE '\b(ARKit|ARSession|ARConfiguration|RealityKit)\b' "$SOURCES" --include='*.swift' 2>/dev/null); then
    echo "error: ARKit reached the capture app target. D-015 forbids it; see ARCHITECTURE.md section 2." >&2
    echo "$hits" | sed 's/^/error: /' >&2
    exit 1
fi
echo "no-arkit check passed: $SOURCES"
