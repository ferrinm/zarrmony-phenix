# Flat-field correction is always-on, always float32, with no toggle

When Opera Phenix experiments ship per-channel FFC profiles, this adapter
applies them automatically and emits `float32`. The math is per-channel
polynomial illumination divide — small `(Y, X)` tile per channel — so it
composes cleanly with zarrmony's chunked streaming via `dask.array.map_blocks`
(the README's prior claim that FFC required eager whole-stack loads described
how `pyphenix.read_data` happens to glue its primitives, not the math itself).
There is no `--flat-field` / `--no-flat-field` flag because zarrmony's reader
plugin contract is path-only with no kwargs, and the presence of profiles in
the export is itself the user's intent signal.

We considered three alternatives. Requantizing back to `uint16` after division
would preserve dtype and on-disk size at the cost of a lossy round-trip — anyone
enabling FFC almost certainly cares about preserved intensities, so we keep the
float32 output pyphenix's `apply_ffc` produces natively. Surfacing a toggle via
environment variable (e.g. `ZARRMONY_PHENIX_FFC=off`) bypasses the CLI contract
instead of fixing it and is undiscoverable. Extending zarrmony's plugin contract
to thread reader-specific kwargs through `convert()` is the right escalation if
many reader-specific knobs eventually accumulate, but is far larger than this
one decision warrants and has no second use case yet.

The escape hatch for users who need raw `uint16` or a no-FFC pipeline is
documented in the README: instantiate `pyphenix.OperaPhenixReader` directly and
write the output yourself. Partial profile coverage (some channels covered, some
not) is surfaced as an `FFCCoverageWarning` from pyphenix; the adapter does not
filter or block conversion in that case.
