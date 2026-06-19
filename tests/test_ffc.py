"""FFC integration tests for ``PhenixReader``.

Covers the contract from issue #6 / ADR-0001: when the Phenix export ships
per-channel FFC profiles, the converted DataArray reflects the corrected
pixels and switches to ``float32``; when no profiles ship, output stays
bytewise-identical to the raw acquisition (``uint16``). FFC math is verified
by computing it eagerly off the same dask graph and comparing against the
reference divide.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import dask.array as da
import numpy as np
import pytest
from pyphenix import FFCCoverageWarning, OperaPhenixReader

from tests.conftest import write_synthetic_phenix
from zarrmony_phenix import PhenixReader


def test_no_ffc_profiles_keeps_uint16_passthrough(synthetic_phenix_dir: Path) -> None:
    """Without FFC profiles the output dtype and bytes are unchanged."""
    r = PhenixReader(synthetic_phenix_dir)
    r.set_scene(0)
    xarr = r.xarray_dask_data
    assert xarr.dtype == np.uint16

    reference = OperaPhenixReader(str(synthetic_phenix_dir), verbose=False)
    md = reference.metadata
    raw = np.asarray(
        reference._read_images_lazy(2, 4, [1], md.timepoints, md.channel_ids, md.planes)
    )
    np.testing.assert_array_equal(xarr.values, raw)


def test_ffc_profiles_switch_dtype_to_float32(tmp_path: Path) -> None:
    root = write_synthetic_phenix(tmp_path / "exp", ffc_profiles={1: 2.0})
    r = PhenixReader(root)
    r.set_scene(0)
    xarr = r.xarray_dask_data
    assert xarr.dtype == np.float32


def test_ffc_math_matches_raw_divide_by_tile(tmp_path: Path) -> None:
    """For uniform polynomial coeff=2.0, every pixel should be raw/2.0."""
    root = write_synthetic_phenix(tmp_path / "exp", ffc_profiles={1: 2.0})

    reference = OperaPhenixReader(str(root), verbose=False)
    md = reference.metadata
    raw = np.asarray(
        reference._read_images_lazy(2, 4, [1], md.timepoints, md.channel_ids, md.planes)
    )
    tile = reference.ffc_correction_images()[1]

    r = PhenixReader(root)
    r.set_scene(0)
    corrected = r.xarray_dask_data.values

    expected = raw.astype(np.float32) / tile
    np.testing.assert_allclose(corrected, expected, rtol=1e-6)


def test_ffc_uses_map_blocks_no_eager_load(tmp_path: Path) -> None:
    """The dask graph must stay lazy; no whole-stack load at property access."""
    root = write_synthetic_phenix(tmp_path / "exp", ffc_profiles={1: 2.0})
    r = PhenixReader(root)
    r.set_scene(0)
    xarr = r.xarray_dask_data
    # An xarray-wrapped dask array means we didn't .compute()/np.asarray() eagerly.
    assert isinstance(xarr.data, da.Array)
    # And the underlying op is a map_blocks-style elemwise (no rechunk/load).
    assert "apply_ffc" in str(xarr.data.name) or "_apply_ffc_chunk" in str(xarr.data.name)


def test_partial_coverage_warning_propagates(tmp_path: Path) -> None:
    """An Identity profile on channel 1 trips pyphenix's FFCCoverageWarning."""
    root = write_synthetic_phenix(tmp_path / "exp", ffc_profiles={1: None})
    with pytest.warns(FFCCoverageWarning):
        PhenixReader(root)


def test_identity_only_profiles_skip_ffc(tmp_path: Path) -> None:
    """Identity-only export has no real correction; output should stay uint16."""
    root = write_synthetic_phenix(tmp_path / "exp", ffc_profiles={1: None})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FFCCoverageWarning)
        r = PhenixReader(root)
    r.set_scene(0)
    assert r.xarray_dask_data.dtype == np.uint16
