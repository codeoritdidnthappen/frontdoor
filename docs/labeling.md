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

## Labeling from the phone, for entrances captured after the closeout (TICK-282, #309)

Everything above is the Mac workflow, and it owns the **frozen 53**: the entrances the 2026-09-04
closeout froze, which #302 completes. Nothing on the phone touches them.

Entrances captured **after** that closeout have no template row to fill in, so they are labeled at
the doorway instead. After all six named views of an entrance are captured, **Finish capture**
opens a labeling screen: the same four criteria, the same three answers (**Present**, **Absent**,
**Cannot determine**), no typing and no dictation. The label is saved on the phone first and sent
to the server when there is a network.

Three things about these labels that are easy to get wrong:

- **They are human ground truth, not upload metadata.** They are the reference the model's verdicts
  are scored against, which is why the labeling screen appears *before* any verdict for that
  entrance is shown and why no model output reaches it.
- **They are recorded once.** The server accepts an entrance's four rows and then locks them: an
  identical resend succeeds so a phone can stop retrying, and anything that disagrees is refused.
  Ground truth that can be revised after the verdicts are known is not ground truth.
- **`labeled_at` is the server's date, not the phone's.** A phone's clock is settable.

### v1 storage is ephemeral, deliberately

The deployed server appends to `data/labels.csv` **inside its own container**. Replacing or
redeploying that container loses every row written at runtime. Persistent volumes, a database and
syncing runtime rows back into the repository are all out of scope for TICK-282 — so treat
phone-entered labels as needing to be copied out before any redeploy, until that changes.
