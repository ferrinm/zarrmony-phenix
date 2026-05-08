"""Cheap predicate that identifies an Opera Phenix experiment directory.

Phenix exports come in two on-disk shapes:

- Export format: ``<root>/Images/Index.xml`` (and TIFFs under ``Images/``).
- Archive format: ``<root>/index/<something>.xml`` plus ``<root>/images/``.

Either marker is enough to claim the directory. The matcher is side-effect-free
and never opens a file.
"""

from pathlib import Path


def match(path: Path) -> int | None:
    if not path.is_dir():
        return None
    if (path / "Images" / "Index.xml").is_file():
        return 100
    archive_index = path / "index"
    if archive_index.is_dir():
        for entry in archive_index.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".xml":
                return 100
    return None
