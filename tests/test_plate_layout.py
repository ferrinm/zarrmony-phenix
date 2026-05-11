"""Tests for ``PhenixReader.plate_layout``.

Covers the happy path, structural validation against zarrmony's plate writer,
and the multi-acquisition graceful-degradation contract.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest
from zarrmony.errors import LayoutDowngradeWarning
from zarrmony.readers.plate import Acquisition, PlateLayout
from zarrmony.writers.plate import validate_plate_layout

from tests.conftest import write_synthetic_phenix
from zarrmony_phenix import PhenixReader


def test_plate_layout_is_populated(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert isinstance(r.plate_layout, PlateLayout)


def test_plate_layout_name_is_plate_id(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert r.plate_layout.name == "SYNTHETIC-PLATE-0001"


def test_plate_layout_lists_every_physical_row_and_column(
    synthetic_phenix_dir: Path,
) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    # Conftest fixture declares 16 rows × 24 columns (a 384-well plate).
    assert r.plate_layout.rows == [chr(ord("A") + i) for i in range(16)]
    assert r.plate_layout.columns == [f"{c:02d}" for c in range(1, 25)]


def test_plate_layout_fields_match_scenes(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert len(r.plate_layout.fields) == len(r.scenes)
    for i, pf in enumerate(r.plate_layout.fields):
        assert pf.scene_index == i
        assert re.fullmatch(r"F\d{3}", pf.field_name)


def test_plate_layout_single_acquisition(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert r.plate_layout.acquisitions == [
        Acquisition(id=1, name="SYNTHETIC-PLATE-0001")
    ]
    for pf in r.plate_layout.fields:
        assert pf.acquisition_id == 1


def test_plate_layout_passes_zarrmony_writer_validation(
    synthetic_phenix_dir: Path,
) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    # Should not raise PlateLayoutError.
    validate_plate_layout(r.plate_layout, n_scenes=len(r.scenes))


def test_single_acquisition_emits_no_warning(synthetic_phenix_dir: Path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PhenixReader(synthetic_phenix_dir)
    downgrades = [w for w in caught if issubclass(w.category, LayoutDowngradeWarning)]
    assert downgrades == []


def test_multi_acquisition_emits_downgrade_warning(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    write_synthetic_phenix(
        root,
        wells=[(2, 4)],
        fields_per_well={(2, 4): [1, 2]},
        # Two AcquisitionIDs across the images: only the first should survive.
        acquisition_ids={(2, 4, 1): "1", (2, 4, 2): "2"},
    )
    with pytest.warns(LayoutDowngradeWarning, match="2 distinct acquisitions"):
        r = PhenixReader(root)
    # Only the first acquisition's field survives.
    assert r.scenes == ["F001"]
    assert [(pf.row, pf.column, pf.field_name) for pf in r.plate_layout.fields] == [
        ("B", "04", "F001")
    ]


def test_plate_field_row_column_format(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    pf = r.plate_layout.fields[0]
    assert pf.row == "B"
    assert pf.column == "04"


def test_plate_layout_field_count_matches_well_field_pairs(
    synthetic_phenix_dir: Path,
) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    expected = sum(len(fields) for fields in r._reader.well_field_map.values())
    assert len(r.plate_layout.fields) == expected
