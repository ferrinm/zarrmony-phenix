from pathlib import Path

import pytest
from zarrmony.readers.plugin import ReaderProtocol

from zarrmony_phenix import PhenixReader, plugin


def test_adapter_satisfies_reader_protocol(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert isinstance(r, ReaderProtocol)


def test_layout_hint_is_plate(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert r.layout_hint == "plate"


def test_scenes_encode_plate_coords(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert r.scenes == ["B04-f01"]


def test_xarray_dims_dtype_shape(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    r.set_scene(0)
    xarr = r.xarray_dask_data
    assert xarr.dims == ("T", "C", "Z", "Y", "X")
    assert xarr.shape == (1, 1, 1, 4, 4)
    assert xarr.dtype == "uint16"
    # Coord on C axis carries the channel name.
    assert list(xarr.coords["C"].values) == ["DAPI"]


def test_physical_pixel_sizes_in_microns(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    px = r.physical_pixel_sizes
    # 2.96688E-07 m -> ~0.297 um
    assert px.X == pytest.approx(0.296688, rel=1e-3)
    assert px.Y == pytest.approx(0.296688, rel=1e-3)
    assert px.Z is None  # single z plane


def test_channel_names(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    assert r.channel_names == ["DAPI"]


def test_metadata_returns_raw_xml(synthetic_phenix_dir: Path) -> None:
    r = PhenixReader(synthetic_phenix_dir)
    raw = r.metadata
    assert raw.startswith("<?xml")
    assert "PlateID" in raw


def test_zarrmony_inspect_finds_phenix_plugin(synthetic_phenix_dir: Path) -> None:
    """End-to-end: register the plugin, call zarrmony.api.inspect, check name."""
    from zarrmony.api import inspect
    from zarrmony.readers import plugin as plugin_mod

    snap_plugins = dict(plugin_mod._PLUGINS)
    snap_loaded = plugin_mod._ENTRY_POINTS_LOADED
    plugin_mod._PLUGINS.clear()
    plugin_mod._ENTRY_POINTS_LOADED = True  # skip real entry-point walk
    try:
        plugin_mod.register_plugin(plugin)
        info = inspect(str(synthetic_phenix_dir))
        assert info["reader_plugin"]["name"] == "zarrmony-phenix"
        assert info["reader_plugin"]["distribution"] == "zarrmony-phenix"
        assert info["n_scenes"] == 1
        assert info["scenes"][0]["name"] == "B04-f01"
    finally:
        plugin_mod._PLUGINS.clear()
        plugin_mod._PLUGINS.update(snap_plugins)
        plugin_mod._ENTRY_POINTS_LOADED = snap_loaded
