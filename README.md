# Reframed Mods

The curated catalog and data-only resource-pack foundation for [Reframed](https://github.com/PetzReframed/Reframed).
**This repository does not yet install mods into the game. No runtime asset
adapters are released, and the generated catalog is intentionally empty.**

The planned catalog covers **Breeds, Toyz, Playscenes, Skins, Music**, plus
Clothes, Textures, Sounds, Hosts, Translations, Themes and explicitly registered
other asset types. Categories do not confer permission to execute or mount files.
See the [design](https://github.com/PetzReframed/Reframed-Docs/blob/main/petz/interface/mods.md)
and [contribution guide](CONTRIBUTING.md).

## Local checks

Python 3.11 or newer; standard library only:

```sh
python -I -m unittest discover -s tests -v
python -I tooling/catalog.py validate-repository .
python -I tooling/catalog.py build /path/to/pack --output build/example.petzmod
python -I tooling/catalog.py inspect build/example.petzmod
```

A standalone review pack directory contains `manifest.json` plus exactly its
hash-listed files. `build-version` instead reads a reviewed repository manifest
and the project's `src/` directory. ZIP output uses STORE, stable ordering,
fixed timestamps and fixed permissions. Existing different output is never
overwritten. These checks establish structural integrity, **not** image/audio
safety, native-module compatibility, installability or gameplay correctness.
Synthetic tests deliberately use inert, non-playable bytes; no game assets are
included or redistributed.

## Committed release artifacts

Build a structural release artifact from an explicit commit without checking out
or reading that repository's working files:

```sh
python -I tooling/release.py --trusted-tooling tooling --repository /path/to/source-repository --commit <full-lowercase-40-hex-commit> --manifest mods/publisher/slug/versions/1.0.0/manifest.json --out /path/to/new-output-directory
```

Run the command from a reviewed tooling checkout. `--trusted-tooling` selects
executable validation code and schemas; it must not point to an untrusted pack
submission. The source repository supplies only committed data. Dirty working
files, staged changes and Git replacement objects do not affect the artifact.
Missing objects fail locally; the producer does not download them.

The output directory must not already exist, and its parent must exist. It
contains `release.json` following the existing release schema and
`packages/<archive-SHA256>.petzmod`. Metadata records exact archive size/hash,
expanded size including the canonical embedded manifest, that manifest's hash,
and the source commit. File paths must resolve through Git trees to regular
blobs; symlinks and submodules are rejected. Metadata, per-file and aggregate
bounds are checked before payload reads, and the existing deterministic STORE
builder validates listed bytes and hashes. Existing output is never overwritten.
A failed disk write can leave an incomplete new directory; only successful
validated output is a release artifact.

The record remains `installable: false` and `validation: "structure-only"`.
This command does not publish files, populate the catalog, assert author trust,
or establish runtime compatibility. Repository-wide dependency validation and
publication review remain separate gates; the public index stays empty.

## Contract

- Draft 2020-12 JSON schemas live in `schemas/`. The standard-library validator
  implements only the tested keywords used by these schemas and rejects unknown
  validation keywords. It is not a general-purpose JSON Schema implementation.
- Pack IDs are publisher-qualified; versions are SemVer-shaped release strings.
  Foundation dependency declarations pin exact versions. Broad SemVer ranges,
  dependency downloads, overrides and runtime capabilities are not implemented.
- `compatibility.assetApi: 1` identifies this validation interface, not a shipped
  game adapter. `compatibility.engine` is `*` or an exact `git-<40hex>` build.
- Every asset, preview and notice is listed with path, byte count, SHA-256, type
  and, for runtime assets only, namespaced target. Preview and notice metadata
  must not declare runtime targets. Only `manifest.json` is exempt from its own file list.
- Package bounds: 1,024 listed files, 64 MiB per file, 4 MiB manifest, 256 MiB
  archive/expanded bytes. Paths are portable ASCII, case-insensitive conflict
  checked and cannot escape the pack. No scripts, executable filenames,
  scriptable previews, nested archives, symlinks or unresolved LFS pointers.
- These are structural limits. A renamed malicious payload remains untrusted.
  No package is executable or installable until its type has a reviewed engine
  adapter with separate decoded-resource limits and real runtime acceptance.

`.pet` files are individual animal saves, not breed definitions. Legacy
`.cat`/`.dog` containers and `.toy`/native `.env` modules require explicit
resource parsing and recovered behavior adapters; their suffix is not execution
permission. Editor `.env` saves have a separate serialized-data format. Skins
cannot inject CSS/HTML. Music requires a real bounded audio validator, not just
RIFF magic. Save-dependent resource retention, uninstall, rollback and portable
backup integration remain game-side TODOs.

## CI and engine build integration

`validate.yml` uses the **trusted base revision's tooling and schemas** for PRs.
The submitted checkout is data only; submitted scripts/tests/workflows are never
executed and PR validation receives no publishing secrets. Tooling/schema changes
need maintainer review and a separate trusted test run before adoption. Initial
workflow activation requires this foundation to be reviewed and merged first.

The manual `engine-check.yml` consumes a main-game `game-build-<commit>` Actions
artifact from an explicit workflow run. A maintainer supplies the expected commit
and the trusted SHA-256 of `game-build-contract.json`; the consumer verifies
repository, interface version, exact build identity and artifact bytes. The
optional `ENGINE_ARTIFACT_READ_TOKEN` is a narrowly scoped artifact-read token for
private access, used only by trusted manual dispatch. It is never a publish token
or exposed to PR jobs. No workflow publishes releases.

The source-only engine artifact contract is documented in
[tooling/ENGINE-CONTRACT.md](tooling/ENGINE-CONTRACT.md). Original game resources
remain external and are never included. An unavailable or incompatible artifact
fails explicitly. A structure-only engine build returns **unsupported (exit 2)**.
For decoded validation of music, Toy Case skins and Editor playscenes, supply the
trusted validator contract SHA-256 as well as the build contract pin.

### Hand off a successful package check

After merge, run the manual engine check on the Mods default branch for the
reviewed manifest. Its successful decoded check uploads `validation-receipt.json`
for 30 days. The run summary identifies the artifact, source and engine commits,
and separate SHA-256 values for the package and receipt. Download the artifact
from that exact run and preserve the receipt bytes and independent summary pin.

From a checkout containing the recorded Mods commit, generate a local feed with
the manifest path used in the check and the **receipt SHA-256** from the summary:

```sh
python3 -I tooling/reviewed_feed.py --repository . --commit "$MODS_COMMIT" \
  --expected-engine-commit "$ENGINE_COMMIT" \
  --release "$MANIFEST" validation-receipt.json "$RECEIPT_SHA256" --out reviewed-feed
```

Repeat `--release` for each reviewed version needed by the selection, including
required dependencies. Each receipt must match the same source and engine commits.
The generator rebuilds the packages from committed files, checks their archive
digests against the receipts, and writes to a new output directory. Publication
remains a separate maintainer action.

## Licences

The existing [MIT licence](LICENSE) covers repository tooling/documentation under
its terms. It does **not** automatically license submitted packs. Each project
and each release must declare its own licence, notices and asset provenance.
Do not submit original game resources or third-party assets without distribution
permission. There are no real packs or published catalog releases in this initial
foundation.
