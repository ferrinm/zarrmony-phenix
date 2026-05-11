# zarrmony-phenix

Opera Phenix reader plugin for [zarrmony](https://github.com/ferrinm/zarrmony).
Wraps [`pyphenix.OperaPhenixReader`](https://github.com/ferrinm/pyphenix) so
that `zarrmony convert /path/to/PhenixExperiment` Just Works.

## Install

```bash
pip install zarrmony-phenix
```

This pulls `zarrmony` and `pyphenix` from PyPI as transitive dependencies.

## Verify the plugin registered

```python
from zarrmony.readers.plugin import list_plugins
print([p.name for p in list_plugins()])
# -> [..., 'zarrmony-phenix']
```

## Use

```bash
zarrmony inspect /path/to/PhenixExperiment   # lists fields per well
zarrmony convert /path/to/PhenixExperiment ./out
```

`zarrmony convert` defaults to `--layout auto`, which dispatches to the HCS
plate writer for plate-shaped readers. The output at `./out` is a single
OME-NGFF 0.5 plate store: well groups at `<row>/<column>/` (e.g. `B/04/`)
each containing one image per imaged field. Pass `--layout plate` to make
the choice explicit, or `--layout per-scene` to produce one
`<scene>.ome.zarr` per FOV instead.

Scenes are named with the vendor's native field labels (`F001`, `F002`, …);
plate coordinates live on the `plate_layout` attribute that zarrmony's plate
writer consumes (see the
[reader-plugin authoring guide §9](https://github.com/ferrinm/zarrmony/blob/main/docs/writing-a-reader-plugin.md#9-writing-a-plate-shaped-reader)
and zarrmony [ADR-0004](https://github.com/ferrinm/zarrmony/blob/main/docs/adr/0004-plate-output-design.md)).
Multi-acquisition Phenix experiments emit a `LayoutDowngradeWarning` and
only the first acquisition's fields are exported; pass `--layout per-scene`
to get all acquisitions in one pass.

### Migrating from v0.1.0

- Scene names changed from `<row-letter><col>-f<field>` (e.g. `B04-f02`)
  to vendor-native field labels (`F001`, `F002`, …). Code that keys
  `--per-scene-metadata` (or anything else) by the old name must be
  re-keyed; plate coordinates now live on `reader.plate_layout`, not in
  the scene name.
- Default output is now a single plate store, not one
  `.ome.zarr` per FOV. Pass `--layout per-scene` to keep the v0.1.0 shape.
- `zarrmony>=0.3.0` is now required (the plate writer ships there).

## Supported Phenix exports

- **Export format**: directory with `Images/Index.xml` and TIFFs under
  `Images/`.
- **Archive format**: directory with `index/<something>.xml` and TIFFs under
  `images/`.

Detection is by the presence of either marker; both are scored equally.

## Limitations

- **Flat-field correction is disabled.** zarrmony streams data into Zarr
  chunk-by-chunk and pyphenix's FFC pipeline requires loading whole stacks
  eagerly. If you need FFC-corrected output, run pyphenix's own loader and
  feed the corrected NumPy arrays into a custom writer.
- **Multi-acquisition Phenix experiments degrade gracefully.** Zarrmony's
  v1 plate writer is single-acquisition; if more than one `AcquisitionID`
  is detected in `Index.xml`, the adapter emits a `LayoutDowngradeWarning`
  and exports only the first acquisition's fields. Pass
  `--layout per-scene` to capture every acquisition as its own store.

## Why a separate package?

Phenix carries real domain logic (FFC math, plate-coordinate parsing, mosaic
stitching) and dependencies (PIL, custom XML parsing) that don't belong in
zarrmony's import graph. See zarrmony [ADR-0003](https://github.com/ferrinm/zarrmony/blob/main/docs/adr/0003-external-adapter-package-for-non-bioio-readers.md)
for the full rationale and the
[reader-plugin authoring guide](https://github.com/ferrinm/zarrmony/blob/main/docs/writing-a-reader-plugin.md)
for how to build your own.

## License

Apache-2.0.
