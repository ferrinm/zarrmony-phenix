# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-11

### Changed (BREAKING)

- `PhenixReader.scenes` now contains vendor-native field labels (`F001`,
  `F002`, ...) instead of the v0.1.0 `<row-letter><col>-f<field>` encoding
  (`B04-f02`). Plate coordinates live on the new `plate_layout` attribute.
  Code that keys `--per-scene-metadata` (or any other lookup) by the old
  scene-name format must be re-keyed to the new `F\d{3}` shape.

### Added

- `PhenixReader.plate_layout` is now a populated `PlateLayout`, so
  `zarrmony convert` with `--layout auto` (or `--layout plate`) writes a
  single OME-NGFF 0.5 plate store.

### Changed

- Bumped `zarrmony>=0.3.0` (the plate writer was added there).
- Multi-acquisition Phenix experiments emit a `LayoutDowngradeWarning`
  and only the first acquisition's fields are exported.

## [0.1.0] — 2026-05-08

### Added

- Initial release. `PhenixReader` adapter wraps `pyphenix.OperaPhenixReader`
  and satisfies zarrmony's `ReaderProtocol`. Registers as `zarrmony-phenix`
  via the `zarrmony.readers` entry point.
- Scenes flatten `(well, field)` pairs into names like `B04-f02` so plate
  coordinates remain recoverable from flat output (zarrmony ADR-0002).
- `layout_hint = "plate"` set from day one; zarrmony 0.2.x ignores the hint
  and emits per-scene flat output until HCS-Plate writer support lands.
- Detects both Phenix on-disk shapes: export (`Images/Index.xml`) and archive
  (`index/*.xml`).
