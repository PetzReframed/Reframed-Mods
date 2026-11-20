"""Opt-in package content validation with code from an independently pinned engine archive."""
import io
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from catalog import Invalid, MAX_TOTAL, inspect_archive, json_bytes, read_file, require, sha

ENTRY = 'tools/validate_mod_package.mjs'
TYPES = ['music', 'playscenes', 'skins']
FILES = {ENTRY, 'engine-files.json', 'package.json', 'web/vendor/fflate.js',
         'web/browser-mod-pack.js', 'web/browser-mod-music-storage.js', 'web/browser-mod-music-profile.js',
         'web/browser-mod-content-types.js', 'web/browser-mod-engine.js', 'web/browser-file-backup.js',
         'web/browser-mod-manifest-schema.js', 'web/browser-playscene-file.js'}


def validate_content(engine, directory, expected_sha, package):
    raw = read_file(directory, 'game-validator-contract.json', 1024 * 1024)
    require(sha(raw) == expected_sha, 'Validator contract hash mismatch')
    artifact = engine['artifacts'][0]
    expected = {'validatorContractVersion': 1, 'repository': engine['repository'], 'sourceCommit': engine['sourceCommit'],
                'engineVersion': engine['engineVersion'], 'assetApi': 1, 'validatedAssetTypes': TYPES,
                'artifact': artifact, 'entrypoint': ENTRY, 'minimumNodeVersion': '22.13.0',
                'input': 'one-package-path', 'output': 'json-result-v1', 'originalAssetsRequired': False}
    descriptor = json_bytes(raw)
    require(descriptor == expected and type(descriptor['validatorContractVersion']) is int and
            type(descriptor['assetApi']) is int and descriptor['originalAssetsRequired'] is False, 'Unsupported validator contract')
    engine_bytes = read_file(directory, artifact['path'], MAX_TOTAL)
    require(sha(engine_bytes) == artifact['sha256'] and len(engine_bytes) == artifact['bytes'], 'Engine artifact bytes mismatch')
    data = read_file(package.parent, package.name, MAX_TOTAL)
    manifest, _ = inspect_archive(data)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(engine_bytes)) as archive:
            require(set(FILES) <= set(archive.namelist()), 'Validator is incomplete')
            for name in FILES:
                info = archive.getinfo(name)
                require(info.compress_type == zipfile.ZIP_STORED and info.file_size <= MAX_TOTAL, 'Invalid engine member')
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        (root/'candidate.petzmod').write_bytes(data)
        try:
            result = subprocess.run(['node', ENTRY, 'candidate.petzmod'], cwd=root, timeout=90, capture_output=True,
                                    env={k: os.environ[k] for k in ('PATH', 'SystemRoot') if k in os.environ})
        except subprocess.TimeoutExpired as exc:
            raise Invalid('Validator timed out') from exc
        require(len(result.stdout) <= 16384, 'Validator result exceeds limit')
        answer = json_bytes(result.stdout)
        require(result.returncode == 0 and answer.get('valid') is True, 'Package content rejected: ' + str(answer.get('code', 'validator-error'))[:80])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest_sha = sha(archive.read('manifest.json'))
        expected_result = {'resultVersion': 1, 'valid': True, 'engineVersion': engine['engineVersion'],
                           'id': manifest['id'], 'version': manifest['version'], 'archiveSha256': sha(data),
                           'archiveBytes': len(data), 'manifestSha256': manifest_sha,
                           'assetTypes': sorted({r['type'] for r in manifest['files']} - {'notice', 'preview'})}
        require(answer == expected_result, 'Validator result differs from the reviewed package')
        return answer
