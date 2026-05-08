# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
