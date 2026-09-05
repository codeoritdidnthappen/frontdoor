#!/usr/bin/env python3
"""Executable percent-format notebook for TICK-100 (#70).

Open this file as a notebook in Jupyter or VS Code, or run every cell from a
clean checkout with the command documented in docs/error-analysis.md. Metric
arithmetic and rendering deliberately live in frontdoor.error_analysis so this
notebook remains a presentation layer over the evaluation harness output.
"""

# %% [markdown]
# # Frontdoor screening error analysis
#
# The screening report supplies all observed metrics. The separate rise-error
# artifact is a prediction derived before data existed, not an observed result.

# %%
import argparse
from pathlib import Path

from frontdoor.error_analysis import generate_figures


# %%
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--budget",
        type=Path,
        default=Path("docs/rise-error-budget.json"),
    )
    return parser.parse_args()


# %%
if __name__ == "__main__":
    arguments = parse_args()
    generate_figures(arguments.report, arguments.budget, arguments.out)
