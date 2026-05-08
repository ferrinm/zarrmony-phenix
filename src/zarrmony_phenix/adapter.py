"""Adapter mapping ``pyphenix.OperaPhenixReader`` onto zarrmony's ReaderProtocol.

Scenes are flattened from (well, field) pairs and named with plate coordinates
(``"B04-f02"``) so plate structure remains recoverable from a flat conversion
once HCS-Plate writer support lands in zarrmony (see zarrmony ADR-0002).
``layout_hint = "plate"`` is set from day one; zarrmony 0.2.x ignores it and
falls back to per-scene flat output.

Lazy loading is forced on (``apply_ffc=False``) because flat-field correction
is incompatible with pyphenix's lazy mode and zarrmony streams data into Zarr
chunk-by-chunk; loading the full plate eagerly would defeat the point.
"""

from dataclasses import dataclass
from pathlib import Path

import dask.array as da
import xarray as xr
from pyphenix import OperaPhenixReader


@dataclass(frozen=True)
class _PixelSizes:
    X: float | None
    Y: float | None
    Z: float | None


def _row_to_letter(row: int) -> str:
    return chr(ord("A") + row - 1)


def _scene_name(row: int, col: int, field: int) -> str:
    return f"{_row_to_letter(row)}{col:02d}-f{field:02d}"


class PhenixReader:
    layout_hint = "plate"

    def __init__(self, path: Path) -> None:
        self._reader = OperaPhenixReader(str(path), verbose=False)
        self._scene_keys: list[tuple[int, int, int]] = []
        for (row, col), fields in sorted(self._reader.well_field_map.items()):
            for field in fields:
                self._scene_keys.append((row, col, field))
        self.scenes: list[str] = [_scene_name(*k) for k in self._scene_keys]
        self._active = 0

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
