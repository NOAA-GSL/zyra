import importlib.util as _ils
import sys
from datetime import datetime
from pathlib import Path

# -- Path setup --------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# -- Project information -----------------------------------------------------

project = "DataVizHub"
author = "NOAA-GSL"
copyright = f"{datetime.now():%Y}, {author}"

# -- General configuration ---------------------------------------------------

extensions = [
    "myst_parser",  # Enable Markdown support
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Napoleon settings for NumPy-style docstrings
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = False
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# -- Options for HTML output -------------------------------------------------

# Default to alabaster; override if RTD theme is available
html_theme = "alabaster"
if _ils.find_spec("sphinx_rtd_theme") is not None:  # pragma: no cover - docs build env
    html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# Autosummary/napoleon tweaks for cleaner API pages
autosummary_generate = True
autosummary_imported_members = False
if html_theme == "sphinx_rtd_theme":
    html_theme_options = {
        "navigation_depth": 3,
        "collapse_navigation": False,
        "sticky_navigation": True,
    }
else:
    html_theme_options = {}

# Support both .rst and .md sources
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Mock optional heavy dependencies to allow building API docs without extras
autodoc_mock_imports = [
    "boto3",
    "botocore",
    "fastapi",
    "uvicorn",
    "vimeo",
    "requests",
    "cartopy",
    "matplotlib",
    "numpy",
    "pygrib",
    "siphon",
    "scipy",
    "netcdf4",
    "xarray",
    "ffmpeg",
    "ffmpeg_python",
    "ffmpeg-python",
    # Mock API submodules that cause side effects on import during docs build
    "datavizhub.api",
    "datavizhub.api.server",
    "datavizhub.api.routers",
    "datavizhub.api.routers.cli",
    "datavizhub.api.routers.files",
    "datavizhub.api.workers",
    "datavizhub.api.workers.executor",
    "datavizhub.api.workers.jobs",
]
