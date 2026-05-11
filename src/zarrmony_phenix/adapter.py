"""Adapter mapping ``pyphenix.OperaPhenixReader`` onto zarrmony's ReaderProtocol.

``layout_hint = "plate"`` and a populated ``plate_layout: PlateLayout`` are
exposed so zarrmony's HCS-Plate writer dispatches on ``--layout auto``. Scene
names are vendor-native (``F001``, ``F002``, ...); plate coordinates live on
``plate_layout``, not the scene name. Per-scene fallback relies on zarrmony's
``resolve_scene_dirnames`` to disambiguate duplicate field labels.

Lazy loading is forced on (``apply_ffc=False``) because flat-field correction
is incompatible with pyphenix's lazy mode and zarrmony streams data into Zarr
chunk-by-chunk; loading the full plate eagerly would defeat the point.
"""

from __future__ import annotations

import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import dask.array as da
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
