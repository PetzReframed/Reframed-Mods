# Main-game artifact consumer contract, version 1

The producer supplies `game-build-contract.json` and `petz5reframed-engine.zip`
in one Actions artifact named `game-build-<sourceCommit>`.

```json
{
  "contractVersion": 1,
  "repository": "PetzReframed/Reframed",
  "sourceCommit": "<40 lowercase hex>",
  "engineVersion": "git-<same commit>",
  "assetApi": 1,
  "supportedAssetTypes": [],
  "capabilities": {
    "validationStatus": "no-runtime-adapters",
    "externalOriginalAssetsRequired": true
  },
  "artifacts": [{
    "path": "petz5reframed-engine.zip",
    "bytes": 123,
    "sha256": "<64 lowercase hex>"
  }]
}
```

The check also accepts the repository's former name, `PetzReframed/Petz5Reframed`, which game builds made under that name carry.

Expected commit and contract SHA-256 come from an approved build, not from the
submitted pack or downloaded contract itself. The consumer verifies those first,
then all referenced bytes. It does not extract or execute the ZIP. Producer
allowlisting is responsible for excluding original resources, saved pets, secrets
and local data. The contract is not a licence grant or proof of runtime support.

`python -I tooling/engine_check.py --engine <directory> --expected-commit <sha>
--expected-contract-sha256 <sha256> --package <pack>` verifies identity and emits
a machine-readable result. Exit 1 is invalid/mismatched input; exit 2 is valid
structural input with unavailable runtime adapters. No exit-0 gameplay acceptance
exists in version 1. A later interface must add real decoded-asset/native runtime
validation before advertising supported types.

## Opt-in engine package validator

Supply the separate trusted `validator_contract_sha256` workflow input (CLI
`--expected-validator-sha256`) to validate the reviewed archive's contents with
Node 24 and the exact engine artifact. The legacy pin is still required. The
consumer verifies the engine ZIP, extracts the validator and its dependencies,
and checks the returned package identity, both hashes, byte count and content
types. Exit 0 records successful engine content validation. Publication, catalog
admission, dependency resolution and in-game testing remain separate steps.

The opted-in manual workflow uploads `validation-receipt.json` and reports its
SHA-256 in the workflow summary. For a local catalog release build, obtain the
receipt and its pin from that trusted run, and supply `--validation-receipt`,
`--expected-receipt-sha256` and `--expected-engine-commit` to `tooling/release.py`.
The producer rebuilds the reviewed Mods commit, checks the exact archive and
embedded manifest against the receipt, and writes the receipt beside release.json.
The release records `engine-content` for the pinned engine. Installation and
publication remain disabled. Omitting the three options produces structure-only output.

## Local installable feed generation

Use trusted tooling on a reviewed Mods commit. Give each release its own manifest
path, receipt from the successful validation workflow and independently trusted
receipt hash. The destination must be new. For example:

```sh
python -I tooling/reviewed_feed.py --repository . --commit "$MODS_COMMIT" \\
  --expected-engine-commit "$ENGINE_COMMIT" --out build/reviewed-feed \\
  --release "$MANIFEST" "$RECEIPT" "$RECEIPT_SHA256"
```

Repeat `--release` for every approved version, including required dependencies.
The output directory contains a browser index, project records, immutable packages
and their original receipts under `evidence/<package-sha256>.json`. Installable
rows apply only to the engine commit tested, including when a manifest declares
`*`. Optional dependencies may be absent. Required closures must fit the browser
resolver and have compatible exact versions, conflicts and playscene names. Saved
room names and current selection constraints are checked by the destination game.
The command writes a local feed only and does not change catalog/v1/index.json.
