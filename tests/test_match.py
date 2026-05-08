from pathlib import Path

from zarrmony_phenix.match import match


def test_match_export_format(synthetic_phenix_dir: Path) -> None:
    assert match(synthetic_phenix_dir) == 100


def test_match_archive_format(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    (root / "index").mkdir(parents=True)
    (root / "index" / "Index.xml").write_text("<x/>")
    assert match(root) == 100


def test_match_unrelated_dir(tmp_path: Path) -> None:
    assert match(tmp_path) is None


def test_match_file_not_dir(tmp_path: Path) -> None:
    f = tmp_path / "x.tif"
    f.write_bytes(b"")
    assert match(f) is None


def test_match_missing_index_xml(tmp_path: Path) -> None:
    (tmp_path / "Images").mkdir()
    assert match(tmp_path) is None
