# Main-game artifact consumer contract, version 1

The producer supplies `game-build-contract.json` and `petz5reframed-engine.zip`
in one Actions artifact named `game-build-<sourceCommit>`.

```json
{
  "contractVersion": 1,
  "repository": "PetzReframed/Petz5Reframed",
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
