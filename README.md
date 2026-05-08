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
zarrmony inspect /path/to/PhenixExperiment   # lists scenes per (well, field)
zarrmony convert /path/to/PhenixExperiment ./out
```

Each scene is named `<row-letter><col>-f<field>` (e.g. `B04-f02`). Plate
coordinates are encoded in scene names so they are recoverable once zarrmony's
HCS-Plate writer support lands (see zarrmony [ADR-0002](https://github.com/ferrinm/zarrmony/blob/main/docs/adr/0002-layout-hint-reservation.md)).
The plugin sets `layout_hint = "plate"` from day one; zarrmony 0.2.x ignores
this hint and falls back to flat per-scene output.

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
- **No HCS-Plate output yet.** Until zarrmony's plate-writer ships, output
  is one `.ome.zarr` store per `(well, field)` scene.

## Why a separate package?

Phenix carries real domain logic (FFC math, plate-coordinate parsing, mosaic
stitching) and dependencies (PIL, custom XML parsing) that don't belong in
zarrmony's import graph. See zarrmony [ADR-0003](https://github.com/ferrinm/zarrmony/blob/main/docs/adr/0003-external-adapter-package-for-non-bioio-readers.md)
for the full rationale and the
[reader-plugin authoring guide](https://github.com/ferrinm/zarrmony/blob/main/docs/writing-a-reader-plugin.md)
for how to build your own.

## License

Apache-2.0.
