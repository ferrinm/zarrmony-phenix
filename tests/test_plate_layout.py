"""Tests for ``PhenixReader.plate_layout``.

Covers the happy path, sparse-plate semantics, structural validation against
zarrmony's plate writer, ordering invariants, multi-acquisition graceful
degradation, defensive parse-failure fallback, and the end-to-end conversion
paths (plate write + per-scene fallback collision behavior).
"""

from __future__ import annotations

import json
import re
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from zarrmony.errors import LayoutDowngradeWarning
from zarrmony.readers.plate import Acquisition, PlateLayout
from zarrmony.writers.plate import validate_plate_layout

from tests.conftest import write_synthetic_phenix
from zarrmony_phenix import PhenixReader, plugin

# ---------------------------------------------------------------------------
# Plugin registration helper for end-to-end tests.
# ---------------------------------------------------------------------------


@pytest.fixture
def registered_plugin():
    """Register the zarrmony-phenix plugin for the duration of one test.

    Mirrors the registry-snapshotting pattern used in ``test_adapter.py``.
    """
    from zarrmony.readers import plugin as plugin_mod

    snap_plugins = dict(plugin_mod._PLUGINS)
    snap_loaded = plugin_mod._ENTRY_POINTS_LOADED
    plugin_mod._PLUGINS.clear()
    plugin_mod._ENTRY_POINTS_LOADED = True
    try:
        plugin_mod.register_plugin(plugin)
        yield
    finally:
        plugin_mod._PLUGINS.clear()
        plugin_mod._PLUGINS.update(snap_plugins)
        plugin_mod._ENTRY_POINTS_LOADED = snap_loaded


# ---------------------------------------------------------------------------
# Happy path — single well, single field.
# ---------------------------------------------------------------------------


def test_plate_layout_is_populated(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert isinstance(r.plate_layout, PlateLayout)


def test_plate_layout_name_is_plate_id(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert r.plate_layout.name == "SYNTHETIC-PLATE-0001"


def test_plate_layout_passes_zarrmony_writer_validation(
    synthetic_phenix_dir: Path,
) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    validate_plate_layout(r.plate_layout, n_scenes=len(r.scenes))


def test_plate_field_row_column_format(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    pf = r.plate_layout.fields[0]
    assert pf.row == "B"
    assert pf.column == "04"


# ---------------------------------------------------------------------------
# Sparse-plate semantics: every physical row/column is declared even when
# only a few wells are imaged. PlateField count matches imaged FOVs only.
# ---------------------------------------------------------------------------


def test_sparse_96_well_plate_declares_full_grid(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    write_synthetic_phenix(
        root,
        plate_rows=8,
        plate_columns=12,
        wells=[(2, 4), (2, 5), (3, 6), (5, 1), (7, 12), (8, 8)],
    )
    r = PhenixReader(root)
    assert r.plate_layout.rows == [chr(ord("A") + i) for i in range(8)]
    assert r.plate_layout.columns == [f"{c:02d}" for c in range(1, 13)]
    # Six imaged wells × one field each.
    assert len(r.plate_layout.fields) == 6
    imaged = {(pf.row, pf.column) for pf in r.plate_layout.fields}
    assert imaged == {("B", "04"), ("B", "05"), ("C", "06"), ("E", "01"), ("G", "12"), ("H", "08")}


def test_minimal_single_well_single_field(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    write_synthetic_phenix(root, plate_rows=1, plate_columns=1, wells=[(1, 1)])
    r = PhenixReader(root)
    assert r.scenes == ["F001"]
    assert len(r.plate_layout.fields) == 1
    assert r.plate_layout.rows == ["A"]
    assert r.plate_layout.columns == ["01"]


# ---------------------------------------------------------------------------
# Ordering invariants and structural validation.
# ---------------------------------------------------------------------------


def test_multiple_fields_per_well_in_native_order(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    write_synthetic_phenix(
        root,
        wells=[(2, 4)],
        # Intentionally out-of-order field IDs to assert pyphenix's sort.
        fields_per_well={(2, 4): [3, 1, 2]},
    )
    r = PhenixReader(root)
    assert [pf.field_name for pf in r.plate_layout.fields] == ["F001", "F002", "F003"]
    assert r.scenes == ["F001", "F002", "F003"]


def test_scene_index_is_unique_and_bijective(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    write_synthetic_phenix(
        root,
        wells=[(2, 4), (3, 5)],
        fields_per_well={(2, 4): [1, 2], (3, 5): [1]},
    )
    r = PhenixReader(root)
    indices = [pf.scene_index for pf in r.plate_layout.fields]
    assert indices == list(range(len(r.scenes)))
    assert len(set(indices)) == len(indices)


@pytest.mark.parametrize(
    "fields_per_well",
    [
        {(2, 4): [1]},
        {(2, 4): [1, 2, 3]},
        {(2, 4): [1, 2], (3, 5): [1]},
    ],
)
def test_field_name_format_matches_phenix_convention(
    tmp_path: Path,
    fields_per_well,
) -> None:
    root = tmp_path / "experiment"
    write_synthetic_phenix(
        root,
        wells=list(fields_per_well.keys()),
        fields_per_well=fields_per_well,
    )
    r = PhenixReader(root)
    for pf in r.plate_layout.fields:
        assert re.fullmatch(r"F\d{3}", pf.field_name)


def test_acquisitions_id_matches_every_plate_field(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert r.plate_layout.acquisitions == [Acquisition(id=1, name="SYNTHETIC-PLATE-0001")]
    acq_ids = {a.id for a in r.plate_layout.acquisitions}
    for pf in r.plate_layout.fields:
        assert pf.acquisition_id in acq_ids


# ---------------------------------------------------------------------------
# Multi-acquisition: warning when multi, silence when single, defensive
# fallback when our scan can't parse.
# ---------------------------------------------------------------------------


def test_multi_acquisition_emits_downgrade_warning(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    write_synthetic_phenix(
        root,
        wells=[(2, 4)],
        fields_per_well={(2, 4): [1, 2]},
        acquisition_ids={(2, 4, 1): "1", (2, 4, 2): "2"},
    )
    with pytest.warns(LayoutDowngradeWarning, match="2 distinct acquisitions"):
        r = PhenixReader(root)
    assert r.scenes == ["F001"]
    assert [(pf.row, pf.column, pf.field_name) for pf in r.plate_layout.fields] == [
        ("B", "04", "F001")
    ]


def test_single_acquisition_emits_no_warning(synthetic_phenix_dir: Path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PhenixReader(synthetic_phenix_dir)
    downgrades = [w for w in caught if issubclass(w.category, LayoutDowngradeWarning)]
    assert downgrades == []


def test_acquisition_scan_parse_failure_falls_back_silently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If our AcquisitionID scan can't parse the XML, treat as single-acquisition.

    pyphenix has already opened the file by the time our scan runs, so a truly
    malformed Index.xml would have failed earlier. We simulate the scan-only
    failure by patching ``ET.parse`` to raise during the adapter's scan only.
    """
    root = tmp_path / "experiment"
    write_synthetic_phenix(root)

    pyphenix_done = {"flag": False}
    real_parse = ET.parse

    def flaky_parse(source, *args, **kwargs):
        # Let pyphenix parse normally; raise once it hands off to our adapter.
        if pyphenix_done["flag"]:
            raise ET.ParseError("simulated scan failure")
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr("zarrmony_phenix.adapter.ET.parse", flaky_parse, raising=True)
    # Flip the flag once OperaPhenixReader has finished parsing.
    from pyphenix import OperaPhenixReader

    real_init = OperaPhenixReader.__init__

    def patched_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        pyphenix_done["flag"] = True

    monkeypatch.setattr(OperaPhenixReader, "__init__", patched_init)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        r = PhenixReader(root)
    downgrades = [w for w in caught if issubclass(w.category, LayoutDowngradeWarning)]
    assert downgrades == []
    assert r.scenes == ["F001"]


# ---------------------------------------------------------------------------
# End-to-end: plate write produces a valid OME-NGFF 0.5 plate store, and
# per-scene fallback disambiguates duplicate vendor-native field labels.
# ---------------------------------------------------------------------------


def _read_zarr_attrs(group_path: Path) -> dict:
    return json.loads((group_path / "zarr.json").read_text())["attributes"]


def test_convert_plate_writes_ome_ngff_plate_store(tmp_path: Path, registered_plugin) -> None:
    from zarrmony.api import convert

    root = tmp_path / "experiment"
    write_synthetic_phenix(
        root,
        wells=[(2, 4), (3, 5)],
        fields_per_well={(2, 4): [1, 2], (3, 5): [1]},
    )
    out = tmp_path / "out.ome.zarr"
    convert(str(root), str(out), layout="plate", permissive=True)

    attrs = _read_zarr_attrs(out)
    plate_meta = attrs["ome"]["plate"]
    assert plate_meta["name"] == "SYNTHETIC-PLATE-0001"
    well_paths = sorted(w["path"] for w in plate_meta["wells"])
    assert well_paths == ["B/04", "C/05"]
    # Well groups exist on disk.
    assert (out / "B" / "04").is_dir()
    assert (out / "C" / "05").is_dir()


def test_per_scene_fallback_disambiguates_duplicate_field_labels(
    tmp_path: Path, registered_plugin
) -> None:
    from zarrmony.api import convert

    root = tmp_path / "experiment"
    write_synthetic_phenix(
        root,
        wells=[(2, 4), (3, 5)],
        # F001 appears in two wells — sanitized names will collide.
        fields_per_well={(2, 4): [1], (3, 5): [1]},
    )
    out = tmp_path / "out_perscene"
    with pytest.warns(LayoutDowngradeWarning):
        convert(str(root), str(out), layout="per-scene", permissive=True)
    store_names = sorted(p.name for p in out.iterdir() if p.suffix == ".zarr")
    assert store_names == ["F001__0.ome.zarr", "F001__1.ome.zarr"]
