"""Adapter mapping ``pyphenix.OperaPhenixReader`` onto zarrmony's ReaderProtocol.

``layout_hint = "plate"`` and a populated ``plate_layout: PlateLayout`` are
exposed so zarrmony's HCS-Plate writer dispatches on ``--layout auto``. Scene
names are vendor-native (``F001``, ``F002``, ...); plate coordinates live on
``plate_layout``, not the scene name. Per-scene fallback relies on zarrmony's
``resolve_scene_dirnames`` to disambiguate duplicate field labels.

Flat-field correction is auto-applied when the Phenix export ships per-channel
profiles. The per-channel illumination tile is fetched once via
``OperaPhenixReader.ffc_correction_images()`` and divided into each chunk via
``dask.array.map_blocks``, so streaming into Zarr stays chunk-by-chunk. Output
dtype switches to ``float32`` whenever any profile is present (see
``docs/adr/0001-always-on-float32-ffc.md``); FFC-less acquisitions keep their
native ``uint16``.
"""

from __future__ import annotations

import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import dask.array as da
import numpy as np
import xarray as xr
from pyphenix import OperaPhenixReader
from zarrmony.errors import LayoutDowngradeWarning
from zarrmony.readers.plate import Acquisition, PlateField, PlateLayout


@dataclass(frozen=True)
class _PixelSizes:
    X: float | None
    Y: float | None
    Z: float | None


def _row_to_letter(row: int) -> str:
    return chr(ord("A") + row - 1)


def _field_name(field: int) -> str:
    return f"F{field:03d}"


def _distinct_acquisition_ids(index_xml_path: Path) -> list[str]:
    """Return distinct ``AcquisitionID`` values seen on ``Image`` elements.

    Returns ``[]`` if parsing fails or no AcquisitionID elements exist; callers
    treat both as the single-acquisition case.
    """
    try:
        tree = ET.parse(str(index_xml_path))
    except (ET.ParseError, OSError):
        return []
    root = tree.getroot()
    seen: list[str] = []
    seen_set: set[str] = set()
    # Namespace-agnostic iter() — Phenix XML uses a UUID/HarmonyV7 namespace.
    for img in root.iter():
        if not img.tag.endswith("Image"):
            continue
        for child in img:
            if child.tag.endswith("AcquisitionID") and child.text:
                aid = child.text.strip()
                if aid and aid not in seen_set:
                    seen_set.add(aid)
                    seen.append(aid)
                break
    return seen


def _apply_ffc_chunk(
    chunk: np.ndarray,
    *,
    channel_ids: tuple[int, ...],
    tiles: dict[int, np.ndarray],
) -> np.ndarray:
    """Divide each channel plane in ``chunk`` by its illumination tile.

    ``chunk`` is a ``(T, C, Z, Y, X)`` slice with the full C axis. Channels
    without a real profile pass through (still cast to float32 for output
    uniformity — see ADR-0001).
    """
    out = chunk.astype(np.float32, copy=True)
    for c_idx, ch_id in enumerate(channel_ids):
        tile = tiles.get(ch_id)
        if tile is not None:
            out[:, c_idx, :, :, :] /= tile
    return out


class PhenixReader:
    layout_hint = "plate"

    def __init__(self, path: Path) -> None:
        self._reader = OperaPhenixReader(str(path), verbose=False)
        md = self._reader.metadata

        scene_keys: list[tuple[int, int, int]] = []
        for (row, col), fields in sorted(self._reader.well_field_map.items()):
            for field in fields:
                scene_keys.append((row, col, field))

        acquisition_ids = _distinct_acquisition_ids(Path(self._reader.index_xml_path))
        if len(acquisition_ids) > 1:
            warnings.warn(
                f"Phenix experiment {md.plate_id} has {len(acquisition_ids)} "
                f"distinct acquisitions; only the first is exported. To get all "
                f"acquisitions in one pass, use --layout per-scene.",
                LayoutDowngradeWarning,
                stacklevel=2,
            )
            first = acquisition_ids[0]
            scene_keys = [k for k in scene_keys if self._scene_acquisition_id(k) == first]

        self._scene_keys: list[tuple[int, int, int]] = scene_keys
        self.scenes: list[str] = [_field_name(field) for (_r, _c, field) in scene_keys]

        rows = [_row_to_letter(r) for r in range(1, md.plate_rows + 1)]
        columns = [f"{c:02d}" for c in range(1, md.plate_columns + 1)]
        plate_fields = [
            PlateField(
                scene_index=i,
                row=_row_to_letter(row),
                column=f"{col:02d}",
                field_name=_field_name(field),
                acquisition_id=1,
            )
            for i, (row, col, field) in enumerate(scene_keys)
        ]
        self.plate_layout: PlateLayout = PlateLayout(
            name=md.plate_id,
            rows=rows,
            columns=columns,
            acquisitions=[Acquisition(id=1, name=md.plate_id)],
            fields=plate_fields,
        )
        self._active = 0

        # Per-channel illumination tiles, evaluated once and reused across
        # every chunk. Empty dict when the export ships no FFC profiles (or
        # only Identity ones) — in which case we leave the dtype at uint16.
        # pyphenix emits ``FFCCoverageWarning`` here on partial coverage; we
        # let it propagate (see ADR-0001).
        self._ffc_tiles: dict[int, np.ndarray] = self._reader.ffc_correction_images()

    def _scene_acquisition_id(self, key: tuple[int, int, int]) -> str | None:
        """Look up the AcquisitionID of any image at ``(row, col, field)``.

        Returns ``None`` if no AcquisitionID is recorded for that key — used
        only to filter scenes when multi-acquisition is detected.
        """
        row, col, field = key
        try:
            tree = ET.parse(str(self._reader.index_xml_path))
        except (ET.ParseError, OSError):
            return None
        for img in tree.getroot().iter():
            if not img.tag.endswith("Image"):
                continue
            r = c = f = None
            aid = None
            for child in img:
                tag = child.tag.rsplit("}", 1)[-1]
                if tag == "Row" and child.text:
                    r = int(child.text)
                elif tag == "Col" and child.text:
                    c = int(child.text)
                elif tag == "FieldID" and child.text:
                    f = int(child.text)
                elif tag == "AcquisitionID" and child.text:
                    aid = child.text.strip()
            if (r, c, f) == (row, col, field):
                return aid
        return None

    def set_scene(self, index: int) -> None:
        self._active = index

    @property
    def xarray_dask_data(self) -> xr.DataArray:
        row, col, field = self._scene_keys[self._active]
        md = self._reader.metadata
        lazy = self._reader._read_images_lazy(
            row, col, [field], md.timepoints, md.channel_ids, md.planes
        )
        h, w = md.image_size
        darr = da.from_array(lazy, chunks=(1, 1, 1, h, w))
        if self._ffc_tiles:
            darr = darr.map_blocks(
                _apply_ffc_chunk,
                channel_ids=tuple(md.channel_ids),
                tiles=self._ffc_tiles,
                dtype=np.float32,
            )
        coords = {"C": self.channel_names} if self.channel_names else None
        return xr.DataArray(darr, dims=("T", "C", "Z", "Y", "X"), coords=coords)

    @property
    def physical_pixel_sizes(self) -> _PixelSizes:
        md = self._reader.metadata
        py_m, px_m = md.pixel_size
        return _PixelSizes(
            X=px_m * 1e6 if px_m else None,
            Y=py_m * 1e6 if py_m else None,
            Z=md.z_step * 1e6 if md.z_step else None,
        )

    @property
    def channel_names(self) -> list[str]:
        md = self._reader.metadata
        return [md.channels[ch_id]["name"] for ch_id in md.channel_ids]

    @property
    def metadata(self) -> str:
        return Path(self._reader.index_xml_path).read_text(encoding="utf-8")
