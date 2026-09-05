# Ground-truth labeling on James's Mac

Issue #168 built this ground-truth workflow; issue #302 tracks James completing the study's human
ground truth. Labels are not needed to capture or upload images. They are used later to evaluate
the screening engine and publish the labeled dataset.

These are retrospective labels. The original captures were completed before this workflow existed,
so do not describe the labels as recorded at capture time or on the same day. James should use only
his own original photographs and recollection. The tool never shows model output. If the evidence
does not support either answer, choose **Cannot determine** rather than guessing.

## Run the local labeler

The selected directory must contain James's original images at the relative paths recorded in the
committed sidecars, for example `<PHOTO_ROOT>/E-001/IMG_3217.JPEG`. Every image is checked against
its manifest SHA-256 before it is displayed. The tool never reads Cloudflare R2, including its
sealed partition.

From the repository root, with the development environment active:

```sh
python -m frontdoor_server.labeling_app --images /absolute/path/to/photo/root
```

Open <http://127.0.0.1:8765>. The server binds only to loopback. It creates `data/labels.csv` if
needed and saves each entrance atomically. Stop it with Control-C.

For every eligible entrance, inspect all displayed photographs and select one answer for each of
the four independent criteria:

- Ramp or beveled threshold
- Handrails
- Accessible door hardware
- Accessibility signage

Each answer is **Present**, **Absent**, or **Cannot determine**. Multiple criteria can be present at
the same entrance. Each criterion still receives only one answer. Cannot determine is stored as a
blank `truth`, with James and the labeling date retained to prove that the row was reviewed rather
than untouched.

The output columns are:

```text
entrance_id,criterion,truth,labeled_by,labeled_at
```

Do not run the screening engine or inspect evaluation results while labeling. After all 53 eligible
entrances show as reviewed, validate the completed artifact before using it in #167:

```sh
python -m frontdoor_server.labeling_app --check
```

That command exits unsuccessfully while any eligible entrance remains untouched or the CSV fails
its schema checks. It does not read any photograph or contact R2.

## Future captures on James's iPhone

The Mac workflow above remains the one-time path for the frozen dataset tracked by #302. Future
entrances are labeled in the capture app after all six named views have been saved. **Finish
capture** then shows four fixed rows, each with **Present**, **Absent**, and **Cannot determine**
buttons. James selects every row explicitly; no model answer is shown until the human record is
durably queued on the phone.

The app remembers James's name, retries queued labels with the existing upload credential, and
locks a record after the deployed server accepts it. The server supplies `labeled_at` and appends
the same four-row entrance-level representation to `data/labels.csv`. These labels are human
ground truth, not image-upload metadata, and image upload does not wait for them.

The deployed container has no git checkout, so its default `data/labels.csv` path is a fresh
runtime file. When running the server from a repository checkout, set `FRONTDOOR_LABELS_PATH` to a
path outside the checkout. The endpoint refuses the default there rather than rewriting the
committed frozen label sheet and leaving the repository dirty.
