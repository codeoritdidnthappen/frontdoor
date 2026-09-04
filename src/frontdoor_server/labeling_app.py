"""Loopback-only ground-truth labeling surface for TICK-246 / #168."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from io import BytesIO
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path
from threading import Lock
from typing import Callable

from flask import Flask, Response, jsonify, request, send_file

from frontdoor.dataset_closeout import load_eligible_entrances
from frontdoor.labels import (
    CRITERIA_KEYS,
    LabelError,
    initialize_labeling_sheet,
    labeling_progress,
    read_labeling_sheet,
    require_complete_labeling,
    save_entrance_labels,
)
from frontdoor.manifest import read_manifest


@dataclass(frozen=True)
class LocalPhoto:
    capture_id: str
    entrance_id: str
    relative_path: Path
    sha256: str


def _local_photo(
    image_root: Path, sidecar_dir: Path, row: dict[str, str]
) -> LocalPhoto:
    capture_id = row["capture_id"]
    sidecar_path = sidecar_dir / f"{capture_id}.json"
    try:
        sidecar: object = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LabelError(f"capture {capture_id} has no sidecar") from exc
    except json.JSONDecodeError as exc:
        raise LabelError(f"capture {capture_id} sidecar is not JSON") from exc
    if not isinstance(sidecar, dict) or not isinstance(sidecar.get("image"), dict):
        raise LabelError(f"capture {capture_id} sidecar has no image record")
    relative = sidecar["image"].get("path")
    if not isinstance(relative, str) or not relative:
        raise LabelError(f"capture {capture_id} sidecar has no local image path")
    relative_path = Path(relative)
    root = image_root.resolve()
    photo_path = (root / relative_path).resolve()
    if not photo_path.is_relative_to(root):
        raise LabelError(f"capture {capture_id} image path escapes the local image root")
    return LocalPhoto(
        capture_id, row["entrance_id"], relative_path, row["image_sha256"]
    )


def _verified_photo_bytes(photo: LocalPhoto, image_root: Path) -> bytes:
    root = image_root.resolve()
    path = (root / photo.relative_path).resolve()
    if not path.is_relative_to(root):
        raise LabelError(
            f"capture {photo.capture_id} image path escapes the local image root"
        )
    try:
        payload = path.read_bytes()
    except FileNotFoundError as exc:
        raise LabelError(
            f"local original is missing for capture {photo.capture_id}: {path}"
        ) from exc
    if hashlib.sha256(payload).hexdigest() != photo.sha256:
        raise LabelError(
            f"local original hash does not match capture {photo.capture_id}"
        )
    return payload


def create_labeling_app(
    *,
    manifest_path: Path,
    sidecar_dir: Path,
    closeout_path: Path,
    image_root: Path,
    labels_path: Path,
    labeled_by: str = "James",
    clock: Callable[[], date] | None = None,
    write_token: str | None = None,
) -> Flask:
    """Create the local app; callers must run it on a loopback address."""
    eligible = sorted(
        load_eligible_entrances(closeout_path, manifest_path, sidecar_dir)
    )
    initialize_labeling_sheet(labels_path, eligible)
    photos = [
        _local_photo(image_root, sidecar_dir, row)
        for row in read_manifest(manifest_path)
        if row["entrance_id"] in eligible
    ]
    by_capture = {photo.capture_id: photo for photo in photos}
    token = write_token or secrets.token_urlsafe(32)
    today = clock or date.today
    write_lock = Lock()

    app = Flask(__name__)

    @app.before_request
    def require_loopback_host() -> tuple[dict[str, str], int] | None:
        host = request.host.partition(":")[0].lower()
        if host not in {"127.0.0.1", "localhost"}:
            return {"error": "labeling is available only on localhost"}, 403
        return None

    @app.get("/")
    def page() -> Response:
        html = (
            resources.files("frontdoor_server")
            .joinpath("labeling.html")
            .read_text(encoding="utf-8")
            .replace("__WRITE_TOKEN__", token)
        )
        return Response(html, mimetype="text/html")

    @app.get("/api/entrances")
    def entrances() -> Response:
        rows = read_labeling_sheet(labels_path, eligible)
        choices = {
            entrance_id: {
                row["criterion"]: row["truth"]
                for row in rows
                if row["entrance_id"] == entrance_id
            }
            for entrance_id in eligible
        }
        reviewed = {
            entrance_id: all(
                row["labeled_by"] and row["labeled_at"]
                for row in rows
                if row["entrance_id"] == entrance_id
            )
            for entrance_id in eligible
        }
        return jsonify(
            {
                "criteria": list(CRITERIA_KEYS),
                "entrances": [
                    {
                        "entrance_id": entrance_id,
                        "answers": choices[entrance_id],
                        "reviewed": reviewed[entrance_id],
                        "photos": [
                            {
                                "capture_id": photo.capture_id,
                                "url": f"/photos/{photo.capture_id}",
                            }
                            for photo in photos
                            if photo.entrance_id == entrance_id
                        ],
                    }
                    for entrance_id in eligible
                ],
            }
        )

    @app.get("/photos/<capture_id>")
    def photo(capture_id: str) -> Response:
        selected = by_capture.get(capture_id)
        if selected is None:
            return jsonify({"error": "unknown or ineligible capture"}), 404
        try:
            payload = _verified_photo_bytes(selected, image_root)
        except LabelError as exc:
            return jsonify({"error": str(exc)}), 422
        return send_file(
            BytesIO(payload),
            download_name=selected.relative_path.name,
            max_age=0,
        )

    @app.post("/api/entrances/<entrance_id>")
    def save(entrance_id: str) -> Response:
        supplied = request.headers.get("X-Frontdoor-Labeling-Token", "")
        if not secrets.compare_digest(supplied, token):
            return jsonify({"error": "invalid labeling write token"}), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
            return jsonify({"error": "request must contain an answers object"}), 400
        answers = body["answers"]
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in answers.items()):
            return jsonify({"error": "answer keys and values must be strings"}), 400
        try:
            entrance_photos = [
                photo for photo in photos if photo.entrance_id == entrance_id
            ]
            if not entrance_photos:
                raise LabelError(f"eligible entrance {entrance_id} has no photos")
            for selected in entrance_photos:
                _verified_photo_bytes(selected, image_root)
            with write_lock:
                save_entrance_labels(
                    labels_path,
                    eligible,
                    entrance_id,
                    answers,
                    labeled_by=labeled_by,
                    labeled_at=today(),
                )
        except LabelError as exc:
            return jsonify({"error": str(exc)}), 422
        progress = labeling_progress(labels_path, eligible)
        return jsonify(
            {
                "saved": entrance_id,
                "reviewed_entrances": progress.reviewed_entrances,
                "total_entrances": progress.total_entrances,
                "complete": progress.complete,
            }
        )

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Label the frozen frontdoor dataset from local original photos."
    )
    parser.add_argument("--images", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.csv"))
    parser.add_argument("--sidecars", type=Path, default=Path("data/sidecars"))
    parser.add_argument(
        "--closeout", type=Path, default=Path("data/dataset-closeout.json")
    )
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--check", action="store_true", help="validate that labeling is complete and exit"
    )
    args = parser.parse_args(argv)
    if args.check:
        eligible = sorted(
            load_eligible_entrances(args.closeout, args.manifest, args.sidecars)
        )
        try:
            require_complete_labeling(args.labels, eligible)
        except LabelError as exc:
            parser.error(str(exc))
        print(f"labeling complete: {len(eligible)} eligible entrances reviewed")
        return 0
    if args.images is None:
        parser.error("--images is required unless --check is used")
    app = create_labeling_app(
        manifest_path=args.manifest,
        sidecar_dir=args.sidecars,
        closeout_path=args.closeout,
        image_root=args.images,
        labels_path=args.labels,
    )
    print(f"Open http://127.0.0.1:{args.port} to label the dataset.")
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
