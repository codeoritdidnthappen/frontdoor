"""Every file the server reads at runtime has to be in the installed package.

The fonts shipped, the routes worked locally, the suite was green, and production answered
500 on all three -- because `package-data` did not name `fonts/*` and the wheel therefore
carried none of them. Nothing caught it: the tests run from the source tree, where
`resources.files()` resolves to `src/frontdoor_server` and every file is present whether it
is packaged or not.

The live page had by then dropped its CDN fallback, so the failure was not "fonts 500", it
was the whole type system silently gone -- which is the exact thing self-hosting them was
meant to prevent.
"""

import fnmatch
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "frontdoor_server"


def package_data_globs():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return config["tool"]["setuptools"]["package-data"]["frontdoor_server"]


def covered(relative_path, globs):
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in globs)


def files_the_server_reads():
    """Filenames the app asks `importlib.resources` for, read out of the source.

    A literal in a `.joinpath("...")` chain. Directory hops (`joinpath("fonts")`) are
    resolved by pairing them with the name that follows, which is how the font route is
    written.
    """
    source = (PACKAGE / "app.py").read_text(encoding="utf-8")
    names = set(re.findall(r'\.joinpath\(\s*"([^"]+)"\s*\)', source))
    directories = {name for name in names if (PACKAGE / name).is_dir()}
    concrete = {name for name in names if (PACKAGE / name).is_file()}
    for directory in directories:
        for child in (PACKAGE / directory).iterdir():
            if child.is_file():
                concrete.add(f"{directory}/{child.name}")
    return concrete, directories


def test_the_source_names_only_files_that_exist():
    concrete, _ = files_the_server_reads()
    missing = sorted(name for name in concrete if not (PACKAGE / name).exists())
    assert not missing, f"app.py reads files that are not in the package: {missing}"


@pytest.mark.parametrize("relative_path", sorted(files_the_server_reads()[0]))
def test_every_file_the_server_reads_is_shipped_in_the_wheel(relative_path):
    globs = package_data_globs()
    assert covered(relative_path, globs), (
        f"{relative_path} is read at runtime but no package-data pattern in pyproject.toml "
        f"matches it, so it is absent from the installed package and the route 500s in "
        f"production while every local test passes. Patterns: {globs}"
    )


def test_the_font_directory_is_covered_whole():
    """Named separately because a font added later must not need this test edited."""
    globs = package_data_globs()
    fonts = sorted(p.name for p in (PACKAGE / "fonts").iterdir() if p.is_file())
    assert fonts, "no fonts in the package"
    uncovered = [name for name in fonts if not covered(f"fonts/{name}", globs)]
    assert not uncovered, f"fonts present in the tree but not packaged: {uncovered}"
