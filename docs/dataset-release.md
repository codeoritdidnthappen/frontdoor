# Screening dataset release (TICK-015, #23)

The GitHub release is the published labeled screening dataset. It is not
created until after the audited unsealing run ([#63](https://github.com/codeoritdidnthappen/frontdoor/issues/63)).
Operator presence labels ([#302](https://github.com/codeoritdidnthappen/frontdoor/issues/302))
must be filled first; an all-blank `data/labels.csv` is not the labeled dataset.

This stages the git-side records and writes the notes a third party needs.
It does not upload bytes and it does not call `gh release`.

## Pack

From a clean checkout of the freeze-day commit:

```
python -m frontdoor.dataset_release pack dist/dataset-release
```

The directory will contain `data/manifest.csv`, `data/sidecars/`,
`data/labels.csv`, `src/frontdoor/split_seed.json`, `RELEASE_NOTES.md`,
`OBJECTS.md`, and `SEAL_AUDIT.log` when that file exists. Photograph and
depth bytes stay in the private R2 buckets listed in `OBJECTS.md`.

The command prints `publish_blockers`. If that list is non-empty, do not
publish.

## After #63

1. Pack from the commit that wrote `SEAL_AUDIT.log`.
2. Confirm `publish_blockers` is empty.
3. From a second machine or a fresh clone, download the staged files and
   every object in `OBJECTS.md`, then recompute hashes against
   `data/manifest.csv`. The diff must be empty.
4. Then, and only then, `gh release create`.
