"""zarrmony-phenix — Opera Phenix reader plugin for zarrmony.

Importing this package exposes a ``plugin`` value (a ``ReaderPlugin``) that is
also surfaced via the ``zarrmony.readers`` entry point declared in
``pyproject.toml``. End users do not import from this package directly; they
``pip install zarrmony-phenix`` and zarrmony picks the plugin up automatically.
"""

from pathlib import Path

from zarrmony.readers.plugin import ReaderPlugin

from .adapter import PhenixReader
from .match import match

__all__ = ["PhenixReader", "match", "plugin"]


def _open(path: Path) -> PhenixReader:
    return PhenixReader(path)


plugin = ReaderPlugin(
    name="zarrmony-phenix",
    match=match,
    open=_open,
    distribution="zarrmony-phenix",
    source="entry_point",
)
