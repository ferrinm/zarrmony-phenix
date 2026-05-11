"""Synthetic Phenix-experiment fixtures.

Builds the smallest on-disk tree that ``pyphenix.OperaPhenixReader`` will load:
an ``Images/Index.xml`` with the requested ``Plate``, ``Well``, and ``Image``
elements plus tiny placeholder TIFFs (1×1 channel/plane/timepoint per Image).
The XML structure mirrors what pyphenix's parser actually reads — anything it
doesn't read is omitted.

The default fixture covers the minimal happy path; the lower-level
``write_synthetic_phenix`` factory is used by tests that need sparse plates,
multiple wells, multiple fields per well, malformed XML, or per-image
``AcquisitionID`` values.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import numpy as np
import pytest
import tifffile

NS = "43B2A954-E3C3-47E1-B392-6635266B0DD3/HarmonyV7"

_CHANNEL_ENTRY = """    <Map>
      <Entry ChannelID="1">
        <ChannelName>DAPI</ChannelName>
        <MainExcitationWavelength>405</MainExcitationWavelength>
        <MainEmissionWavelength>450</MainEmissionWavelength>
        <ExposureTime>0.05</ExposureTime>
        <ObjectiveMagnification>20</ObjectiveMagnification>
        <ObjectiveNA>0.8</ObjectiveNA>
        <ImageSizeX>4</ImageSizeX>
        <ImageSizeY>4</ImageSizeY>
        <ImageResolutionX>2.96688132474701E-07</ImageResolutionX>
        <ImageResolutionY>2.96688132474701E-07</ImageResolutionY>
      </Entry>
    </Map>"""


def _well_id(row: int, col: int) -> str:
    return f"{row:02d}{col:02d}"


def _image_url(row: int, col: int, field: int) -> str:
    return f"r{row:02d}c{col:02d}f{field:02d}p01-ch1.tiff"


def _image_xml(row: int, col: int, field: int, acquisition_id: str | None) -> str:
    aid_line = (
        f"      <AcquisitionID>{acquisition_id}</AcquisitionID>\n"
        if acquisition_id is not None
        else ""
    )
    return (
        "    <Image>\n"
        f"      <Row>{row}</Row>\n"
        f"      <Col>{col}</Col>\n"
        f"      <FieldID>{field}</FieldID>\n"
        "      <PlaneID>1</PlaneID>\n"
        "      <TimepointID>1</TimepointID>\n"
        "      <ChannelID>1</ChannelID>\n"
        f"      <URL>{_image_url(row, col, field)}</URL>\n"
        "      <PositionX>0.0</PositionX>\n"
        "      <PositionY>0.0</PositionY>\n"
        "      <PositionZ>0.0</PositionZ>\n"
        "      <MeasurementTimeOffset>0.0</MeasurementTimeOffset>\n"
        f"{aid_line}"
        "    </Image>"
    )


def write_synthetic_phenix(
    root: Path,
    *,
    plate_id: str = "SYNTHETIC-PLATE-0001",
    plate_rows: int = 16,
    plate_columns: int = 24,
    wells: Iterable[tuple[int, int]] = ((2, 4),),
    fields_per_well: Mapping[tuple[int, int], Iterable[int]] | None = None,
    acquisition_ids: Mapping[tuple[int, int, int], str] | None = None,
    index_xml_override: str | None = None,
) -> Path:
    """Write a minimal Phenix experiment tree under ``root``.

    Parameters mirror the structure pyphenix's parser actually reads. Pass
    ``index_xml_override`` to write arbitrary (e.g. malformed) XML for
    defensive-parsing tests.
    """
    images_dir = root / "Images"
    images_dir.mkdir(parents=True, exist_ok=True)

    if index_xml_override is not None:
        (images_dir / "Index.xml").write_text(index_xml_override, encoding="utf-8")
        return root

    fpw = fields_per_well or {w: [1] for w in wells}
    well_xml = "\n".join(f'    <Well id="{_well_id(r, c)}"/>' for (r, c) in wells)

    image_blocks: list[str] = []
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 65535, size=(4, 4), dtype=np.uint16)

    for row, col in wells:
        for field in fpw[(row, col)]:
            aid = (acquisition_ids or {}).get((row, col, field))
            image_blocks.append(_image_xml(row, col, field, aid))
            tifffile.imwrite(images_dir / _image_url(row, col, field), frame)

    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<EvaluationInputData xmlns="{NS}">\n'
        "  <Plate>\n"
        f"    <PlateID>{plate_id}</PlateID>\n"
        "    <MeasurementID>SYNTHETIC-MEAS-0001</MeasurementID>\n"
        f"    <PlateRows>{plate_rows}</PlateRows>\n"
        f"    <PlateColumns>{plate_columns}</PlateColumns>\n"
        f"{well_xml}\n"
        "  </Plate>\n"
        "  <Maps>\n"
        f"{_CHANNEL_ENTRY}\n"
        "  </Maps>\n"
        "  <Images>\n" + "\n".join(image_blocks) + "\n  </Images>\n"
        "</EvaluationInputData>\n"
    )
    (images_dir / "Index.xml").write_text(xml, encoding="utf-8")
    return root


@pytest.fixture
def synthetic_phenix_dir(tmp_path: Path) -> Path:
    return write_synthetic_phenix(tmp_path / "experiment")
