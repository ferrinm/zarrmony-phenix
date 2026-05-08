"""Synthetic Phenix-experiment fixture.

Builds the smallest on-disk tree that ``pyphenix.OperaPhenixReader`` will load:
one well (B04 == row 2, col 4), one field, one timepoint, one channel, one
z-plane, a single 4x4 uint16 TIFF. The XML structure mirrors what
``_parse_metadata`` and ``_parse_timepoint_offsets`` actually read — anything
they don't read is omitted.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import tifffile

NS = "43B2A954-E3C3-47E1-B392-6635266B0DD3/HarmonyV7"

INDEX_XML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<EvaluationInputData xmlns="{ns}">
  <Plate>
    <PlateID>SYNTHETIC-PLATE-0001</PlateID>
    <MeasurementID>SYNTHETIC-MEAS-0001</MeasurementID>
    <PlateRows>16</PlateRows>
    <PlateColumns>24</PlateColumns>
    <Well id="0204"/>
  </Plate>
  <Maps>
    <Map>
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
    </Map>
  </Maps>
  <Images>
    <Image>
      <Row>2</Row>
      <Col>4</Col>
      <FieldID>1</FieldID>
      <PlaneID>1</PlaneID>
      <TimepointID>1</TimepointID>
      <ChannelID>1</ChannelID>
      <URL>r02c04f01p01-ch1.tiff</URL>
      <PositionX>0.0</PositionX>
      <PositionY>0.0</PositionY>
      <PositionZ>0.0</PositionZ>
      <MeasurementTimeOffset>0.0</MeasurementTimeOffset>
    </Image>
  </Images>
</EvaluationInputData>
"""


def _write_synthetic_phenix(root: Path) -> Path:
    images = root / "Images"
    images.mkdir(parents=True, exist_ok=True)
    (images / "Index.xml").write_text(INDEX_XML_TEMPLATE.format(ns=NS), encoding="utf-8")
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 65535, size=(4, 4), dtype=np.uint16)
    tifffile.imwrite(images / "r02c04f01p01-ch1.tiff", frame)
    return root


@pytest.fixture
def synthetic_phenix_dir(tmp_path: Path) -> Path:
    return _write_synthetic_phenix(tmp_path / "experiment")
