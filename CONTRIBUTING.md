# Contributing packs

Submit a pull request; no account credentials or install scripts belong in a pack.
All initial submissions are structural review candidates, not playable releases.

```text
mods/<publisher>/<slug>/
  project.json
  src/
    assets/<registered-category>/...
    preview.png
    notices/LICENSE.txt
    notices/credits.json
  versions/1.0.0/manifest.json
```

`project.json` follows `schemas/project-v1.schema.json`; the ID must match
`<publisher>.<slug>`. A release manifest follows `manifest-v1.schema.json` and
its version must match its directory. Put preview and notices under `src/` and
list them alongside content files using types `preview` and `notice`. Metadata notices/previews have no runtime target. Every
content target uses the pack's namespace, such as `author.example:track-one`.
The root manifest is copied into the package by trusted tooling.

The current repository validator requires exact required dependency versions to
exist in the submitted repository and rejects cycles and self dependencies.
Optional unresolved dependencies are permitted but are not downloaded or enabled.
It does not resolve remote dependencies or broad version ranges.

Run `python -I tooling/catalog.py validate-repository .`, then build a review
artifact with:

```sh
python -I tooling/catalog.py build-version . --manifest mods/author/example/versions/1.0.0/manifest.json --output build/example.petzmod
```

Use your own authored assets and include permission/provenance for each source.
Original Petz assets cannot be included merely because the engine is MIT.
Never put `.pet` player saves or private information into a public submission.
All requested categories are represented in the contract, but no asset category
is currently runtime-supported. Executable modules are not accepted as behavior.

Review covers licence, hashes, metadata, dependency collisions and eventually
engine-specific validation. A structural pass cannot substitute for native
resource decoding, public gameplay use, saving, reload and clean shutdown.
Pack updates require new versions; immutable published versions must not be
rewritten. For now the catalog index remains empty: release publication and
runtime compatibility are intentionally gated.

The game installation lifecycle must protect saved pets, pregnancies, room
checkpoints and referenced assets before removal. Packs must not propose deleting
or rewriting these as an install workaround. Unsupported content needs a separate
reviewed engine adapter, never submitted code executed by the installer.
