# Error-analysis notebook

TICK-100 (#70) presents the metrics already computed by the screening evaluation harness and the
rise-error prediction derived before data existed. It does not read images, manifests, labels, or
object storage, and it cannot unseal anything.
The notebook accepts only a `dev` report; it rejects `sealed`, `calib`, and unknown split values.

From a clean checkout, after producing a dev harness report, run every cell of the executable
percent-format notebook with one command:

```sh
python notebooks/error_analysis.py \
  --report reports/dry-run/screening_eval.json \
  --out reports/error-analysis
```

The output is five SVG figures plus `analysis_manifest.json`. The per-criterion and condition
figures present values from `screening_eval.json`; condition figures identify themselves as
exploratory, show independent-entrance sample sizes, and mark rows below the harness's recorded
minimum as underpowered. The per-criterion figure is also marked exploratory. The predicted chart
uses the committed values in `docs/rise-error-budget.json`, labels itself **predicted — pre-data**,
and discloses that the analytical series used the superseded 2934.1 px focal-length example while
the 3D check used the 2807.7 px value measured on James's iPhone. It must not be described as an
observed result.

`notebooks/error_analysis.py` is a Jupyter/VS Code percent-format notebook (`# %%` cells) that is
also directly executable by Python. This avoids a separate notebook runtime and stale saved
kernel output while preserving top-to-bottom notebook use.
