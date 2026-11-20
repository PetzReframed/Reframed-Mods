"""Build a local browser catalog from individually reviewed releases. No publication or catalog discovery."""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog as c
from release import Committed, produce

SUPPORTED = {'music', 'playscenes', 'skins'}


def check_closure(root, manifests):
    """Check what a clean browser would select for one release, including optional edges inside that selection."""
    chosen = {}

    def gather(key, depth):
        if key in chosen.values():
            return
        c.require(depth <= 16 and len(chosen) < 32, 'Required selection exceeds browser limits')
        c.require(key in manifests, 'Missing reviewed dependency: ' + '@'.join(key))
        ident, version = key
        c.require(ident not in chosen, 'Incompatible required versions: ' + ident)
        chosen[ident] = key
        for dep in manifests[key]['dependencies']:
            if not dep['optional']:
                gather((dep['id'], dep['version']), depth + 1)

    gather(root, 0)
    done, visiting, rooms = set(), set(), set()

    def visit(key, depth):
        c.require(key not in visiting and depth <= 16, 'Dependency cycle or depth exceeded')
        if key in done:
            return
        visiting.add(key)
        manifest = manifests[key]
        c.require(not any(i in chosen for i in manifest['conflicts']), 'Conflicting required selection')
        for dep in manifest['dependencies']:
            target = chosen.get(dep['id'])
            if target:
                c.require(target[1] == dep['version'], 'Incompatible selected dependency')
                visit(target, depth + 1)
        for member in manifest['files']:
            if member['type'] == 'playscenes':
                room = member['target'].split(':', 1)[1].lower()
                c.require(room not in rooms, 'Playscene name collision: ' + room)
                rooms.add(room)
        visiting.remove(key)
        done.add(key)

    for key in sorted(chosen.values()):
        visit(key, 0)


def generate(repo, commit, engine, releases, out):
    c.require(re.fullmatch('[a-f0-9]{40}', engine) is not None, 'Expected pinned engine commit')
    c.require(0 < len(releases) <= 4096, 'Select 1 to 4096 reviewed releases')
    out = Path(out)
    if out.exists() or out.is_symlink():
        raise FileExistsError(out)
    source = Committed(repo, commit)
    projects, manifests, types = {}, {}, set()
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        files = Path(temp) / 'feed'
        for folder in ('packages', 'projects', 'evidence'):
            (files/folder).mkdir(parents=True)
        for i, (path, receipt, pin) in enumerate(releases):
            work = Path(temp) / str(i)
            # Rebuild from Git blobs and compare all package identities to the pinned successful receipt.
            record = produce(c, repo, commit, path, work, receipt=receipt,
                             expected_receipt_sha256=pin, expected_engine_commit=engine)
            key = (record['id'], record['version'])
            c.require(key not in manifests, 'Duplicate reviewed release')
            manifest = c.json_bytes(source.blob(path, c.MAX_JSON))
            manifests[key] = manifest
            content = sorted({f['type'] for f in manifest['files']} - {'notice', 'preview'})
            c.require(content and set(content) <= SUPPORTED, 'Unsupported engine content type')
            types.update(content)
            project = projects.get(key[0])
            if project is None:
                project_path = '/'.join(path.split('/')[:3]) + '/project.json'
                project = {'project': c.checked(c.json_bytes(source.blob(project_path, c.MAX_JSON)), 'project'), 'releases': []}
                projects[key[0]] = project
            releases_out = project['releases']
            c.require(len(releases_out) < 1024, 'Project release limit')
            row = {k:record[k] for k in ('id','version','package','bytes','expandedBytes','sha256','manifestSha256','sourceCommit')}
            row.update(installable=True, validation='engine-adapters', dependencies=manifest['dependencies'],
                       conflicts=manifest['conflicts'], compatibility={**manifest['compatibility'], 'engine':'git-'+engine}, types=content)
            releases_out.append(row)
            (work / row['package']).rename(files / row['package'])
            (work/'validation-receipt.json').rename(files/'evidence'/(row['sha256']+'.json'))
        for key in sorted(manifests):
            check_closure(key, manifests)
        entries = []
        for ident, project in sorted(projects.items()):
            project['releases'].sort(key=lambda r:r['version'])
            path = 'projects/' + ident + '.json'
            data = c.canonical(project)
            c.require(len(data) <= 1024*1024, 'Browser project record size exceeded')
            (files/path).write_bytes(data)
            entries.append({k:project['project'][k] for k in ('id','name','categories')} | {'record':path})
        index = {'catalogVersion':1, 'supportedAssetTypes':sorted(types), 'projects':entries}
        data = c.canonical(index)
        c.require(len(data) <= 4*1024*1024, 'Browser index size exceeded')
        (files/'index.json').write_bytes(data)
        out.mkdir()  # exclusive, after every receipt, dependency closure and output size has been checked
        for name in ('packages','evidence','projects','index.json'):
            (files/name).rename(out/name)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--expected-engine-commit', required=True)
    parser.add_argument('--release', nargs=3, action='append', required=True, metavar=('MANIFEST','RECEIPT','RECEIPT_SHA256'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.repository, args.commit, args.expected_engine_commit, args.release, args.out), sort_keys=True))


if __name__ == '__main__':
    main()
