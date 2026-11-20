"""Trusted, standard-library structural validation. Never executes pack content."""
from __future__ import annotations
import argparse, hashlib, io, json, os, re, stat, tempfile, zipfile
from pathlib import Path, PurePosixPath
from itertools import islice

ROOT = Path(__file__).resolve().parents[1]
MAX_JSON = 4 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILES = 1024
FORBIDDEN = {'.js', '.mjs', '.cjs', '.py', '.exe', '.dll', '.wasm', '.bat', '.cmd', '.ps1', '.sh', '.html', '.htm', '.css', '.svg', '.zip', '.petzmod'}
class Invalid(ValueError): pass

def require(condition, message):
    if not condition: raise Invalid(message)

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf8')

def sha(data): return hashlib.sha256(data).hexdigest()

def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result

def json_bytes(data):
    require(len(data) <= MAX_JSON, 'JSON size limit exceeded')
    try: return json.loads(data.decode('utf8'), object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(Invalid('Non-finite JSON number')))
    except (UnicodeError, json.JSONDecodeError) as exc: raise Invalid('Invalid UTF-8 JSON') from exc

def safe_path(value):
    require(isinstance(value, str) and 0 < len(value) <= 240, 'Invalid relative path')
    require(value.isascii() and '\\' not in value and ':' not in value and not value.startswith('/'), 'Nonportable path: ' + value)
    parts = value.split('/')
    require(all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', p) and p not in {'.', '..'} and not p.endswith('.') for p in parts), 'Unsafe path: ' + value)
    require(not any(re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p) for p in parts), 'Reserved filename')
    return value

def is_link(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))

def read_file(root, relative, limit=MAX_FILE):
    safe_path(relative)
    current = root
    for part in relative.split('/'):
        current = current / part
        require(not is_link(current), 'Links are forbidden: ' + relative)
    require(current.is_file(), 'Missing regular file: ' + relative)
    require(current.stat().st_size <= limit, 'File size limit: ' + relative)
    with current.open('rb') as stream: data = stream.read(limit + 1)
    require(len(data) <= limit, 'File grew beyond size limit')
    return data

def validate_schema(value, schema, at='$'):
    """Deliberately small JSON Schema subset; unknown validation keywords fail closed.

    Schemas shipped here use only these keywords. This is not a general schema engine.
    """
    known = {'$schema', 'title', 'description', 'type', 'const', 'enum', 'properties', 'required', 'additionalProperties', 'propertyNames', 'minProperties', 'maxProperties', 'items', 'minItems', 'maxItems', 'uniqueItems', 'minimum', 'maximum', 'minLength', 'maxLength', 'pattern'}
    require(not set(schema) - known, 'Unsupported schema keyword at ' + at)
    if 'const' in schema: require(type(value) is type(schema['const']) and value == schema['const'], at + ': wrong constant')
    if 'enum' in schema: require(any(type(value) is type(x) and value == x for x in schema['enum']), at + ': invalid enum')
    typ = schema.get('type')
    checks = {'object': isinstance(value, dict), 'array': isinstance(value, list), 'string': isinstance(value, str), 'integer': type(value) is int, 'boolean': type(value) is bool}
    if typ: require(typ in checks and checks[typ], at + ': expected ' + typ)
    if isinstance(value, dict):
        require(set(schema.get('required', [])) <= set(value), at + ': missing required key')
        require(schema.get('minProperties', 0) <= len(value) <= schema.get('maxProperties', 100000), at + ': property count')
        props = schema.get('properties', {})
        for key, child in value.items():
            if 'propertyNames' in schema: validate_schema(key, {'type':'string', **schema['propertyNames']}, at)
            if key in props: validate_schema(child, props[key], at + '.' + key)
            elif schema.get('additionalProperties') is False: raise Invalid(at + ': unknown key ' + key)
            elif isinstance(schema.get('additionalProperties'), dict): validate_schema(child, schema['additionalProperties'], at + '.' + key)
    if isinstance(value, list):
        require(schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', MAX_FILES), at + ': item count')
        if schema.get('uniqueItems'): require(len({canonical(x) for x in value}) == len(value), at + ': duplicate item')
        for index, child in enumerate(value):
            if 'items' in schema: validate_schema(child, schema['items'], f'{at}[{index}]')
    if isinstance(value, str):
        require(schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', MAX_JSON), at + ': string length')
        if 'pattern' in schema: require(re.search(schema['pattern'], value) is not None, at + ': pattern mismatch')
    if type(value) is int: require(schema.get('minimum', value) <= value <= schema.get('maximum', value), at + ': numeric bound')

def schema(name): return json_bytes((ROOT / 'schemas' / (name + '-v1.schema.json')).read_bytes())
def checked(value, name):
    validate_schema(value, schema(name))
    if name=='release':
        engine=value['validation']=='engine-content'
        require(engine==('engineValidation' in value) and engine==(value['unsupportedReason']=='Content validated for one pinned engine. Catalog publication has not been approved.'),'Release validation evidence mismatch')
    return value

def validate_manifest(manifest, files):
    checked(manifest, 'manifest')
    require(manifest['compatibility']['engine'] == '*' or re.fullmatch(r'git-[0-9a-f]{40}', manifest['compatibility']['engine']), 'Foundation engine constraint must be * or an exact git build')
    require(any(r['type'] not in {'preview','notice'} for r in manifest['files']), 'Pack requires at least one content file')
    require(not manifest['overrides'], 'Overrides require a released runtime adapter; v1 foundation rejects them')
    require(not manifest['compatibility']['capabilities'], 'No runtime capabilities are released')
    require(manifest['id'] not in manifest['conflicts'], 'Pack conflicts with itself')
    dependencies = manifest['dependencies']
    require(len({x['id'] for x in dependencies}) == len(dependencies), 'Duplicate dependency ID')
    require(all(x['id'] != manifest['id'] for x in dependencies), 'Self dependency')
    paths, targets, expanded = set(), set(), 0
    for row in manifest['files']:
        path = safe_path(row['path']); key = path.casefold()
        require(path != 'manifest.json' and key not in paths, 'Duplicate/reserved file path')
        paths.add(key)
        require(PurePosixPath(path).suffix.lower() not in FORBIDDEN, 'Executable, scriptable or archive file rejected: ' + path)
        if row['type'] in {'preview','notice'}:
            require('target' not in row and 'behaviorFamily' not in row, 'Metadata must not declare a runtime target or behavior')
        else:
            require('target' in row and row['target'].startswith(manifest['id'] + ':'), 'Target must belong to pack namespace')
            require(row['target'].casefold() not in targets, 'Duplicate target'); targets.add(row['target'].casefold())
        require(row['type'] in {'preview','notice'} or row['type'] in manifest['categories'], 'Asset type absent from categories')
        require('behaviorFamily' not in row, 'Behavior families require a released runtime adapter')
        data = files.get(path); require(isinstance(data, bytes), 'Missing manifest file: ' + path)
        require(len(data) == row['bytes'] and sha(data) == row['sha256'], 'File hash/size mismatch: ' + path)
        expanded += len(data); require(expanded <= MAX_TOTAL, 'Expanded size limit')
        require(not data.startswith(b'version https://git-lfs.github.com/spec/v1'), 'Unresolved Git LFS pointer')
        require(not zipfile.is_zipfile(io.BytesIO(data)), 'Nested ZIP payload rejected regardless of extension')
    require(set(files) == {x['path'] for x in manifest['files']}, 'Unlisted package file')
    by_path = {x['path']: x for x in manifest['files']}
    for path in manifest['notices']:
        require(path in by_path and by_path[path]['type'] == 'notice', 'Notice must be hash-listed with notice type')
    if 'preview' in manifest: require(manifest['preview'] in by_path and by_path[manifest['preview']]['type'] == 'preview', 'Preview must be hash-listed with preview type')
    return expanded

def read_listed_files(directory, manifest, prefix=None):
    checked(manifest, 'manifest')
    require(sum(r['bytes'] for r in manifest['files']) <= MAX_TOTAL, 'Expanded size limit before reads')
    files = {}
    for row in manifest['files']:
        path = row['path'] if prefix is None else safe_path(prefix) + '/' + row['path']
        data = read_file(directory, path, min(row['bytes'], MAX_FILE))
        require(len(data) == row['bytes'], 'Declared file size mismatch')
        files[row['path']] = data
    return files

def load_pack(directory):
    directory = Path(directory).resolve(); raw = read_file(directory, 'manifest.json', MAX_JSON)
    manifest = json_bytes(raw); checked(manifest, 'manifest')
    actual = set()
    for count, path in enumerate(directory.rglob('*'), 1):
        require(count <= MAX_FILES * 4, 'Pack tree entry limit')
        require(not is_link(path), 'Link in pack tree')
        if path.is_file():
            relative = path.relative_to(directory).as_posix(); safe_path(relative)
            if relative != 'manifest.json': actual.add(relative)
            require(len(actual) <= MAX_FILES, 'Pack file count limit')
    require(actual == {r['path'] for r in manifest['files']}, 'Unlisted or missing package file')
    files = read_listed_files(directory, manifest)
    validate_manifest(manifest, files)
    return manifest, files

def build_bytes(manifest, files):
    validate_manifest(manifest, files)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for path, data in sorted({'manifest.json': canonical(manifest), **files}.items()):
            info = zipfile.ZipInfo(path, (1980,1,1,0,0,0)); info.create_system = 3; info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    result = output.getvalue(); require(len(result) <= MAX_TOTAL, 'Archive size limit'); return result

def inspect_archive(data):
    require(len(data) <= MAX_TOTAL, 'Archive size limit')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist(); require(1 <= len(infos) <= MAX_FILES + 1, 'Archive file count')
            files = {}; keys = set(); total = 0
            for info in infos:
                safe_path(info.filename); key = info.filename.casefold()
                require(key not in keys, 'Duplicate archive path'); keys.add(key)
                require(not info.flag_bits & 1 and info.compress_type == zipfile.ZIP_STORED, 'Foundation accepts unencrypted STORE packages only')
                mode = info.external_attr >> 16
                require(stat.S_IFMT(mode) in (0,stat.S_IFREG) and not info.is_dir(), 'Non-regular archive member')
                limit = MAX_JSON if info.filename == 'manifest.json' else MAX_FILE
                require(info.file_size <= limit and info.compress_size == info.file_size, 'Archive member bound')
                total += info.file_size; require(total <= MAX_TOTAL, 'Expanded size limit')
            for info in infos: files[info.filename] = archive.read(info)
            require('manifest.json' in files, 'Missing manifest'); manifest = json_bytes(files.pop('manifest.json'))
            validate_manifest(manifest, files); return manifest, files
    except (zipfile.BadZipFile, EOFError, RuntimeError) as exc: raise Invalid('Malformed ZIP') from exc

def write_immutable(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): require(path.read_bytes() == data, 'Immutable output already differs: ' + str(path)); return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.build-', delete=False) as stream:
            temporary = Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try: os.link(temporary, path)
        except FileExistsError: require(path.read_bytes() == data, 'Concurrent immutable output differs')
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)

def validate_repository(repository):
    repo = Path(repository).resolve(); index = checked(json_bytes(read_file(repo,'catalog/v1/index.json',MAX_JSON)), 'catalog')
    require(index['projects'] == [], 'Foundation index must stay empty until publication tooling and adapters are approved')
    projects = []; releases = {}; metadata_bytes = 0
    def metadata(path):
        nonlocal metadata_bytes
        raw = read_file(repo,path.relative_to(repo).as_posix(),MAX_JSON)
        metadata_bytes += len(raw); require(metadata_bytes <= 32 * 1024 * 1024, 'Repository metadata byte limit')
        return json_bytes(raw)
    def bounded(pattern):
        paths = list(islice((repo/'mods').glob(pattern), 4097))
        require(len(paths) <= 4096, 'Repository entry limit before sorting')
        return sorted(paths)
    for path in bounded('*/*/project.json'):
        project = checked(metadata(path), 'project')
        require(project['id'] == path.parent.parent.name + '.' + path.parent.name, 'Project path/ID mismatch')
        projects.append(project)
        require(len(projects) <= 4096, 'Repository project limit')
    require(len({p['id'] for p in projects}) == len(projects), 'Duplicate project')
    for path in bounded('*/*/versions/*/manifest.json'):
        manifest = checked(metadata(path), 'manifest')
        project = next((p for p in projects if p['id'] == path.parents[3].name + '.' + path.parents[2].name), None)
        require(project is not None and manifest['id'] == project['id'] and manifest['version'] == path.parent.name, 'Version path/project mismatch')
        source = path.parents[2] / 'src'
        files = read_listed_files(repo, manifest, source.relative_to(repo).as_posix())
        validate_manifest(manifest,files)
        releases[(manifest['id'],manifest['version'])] = manifest
        require(len(releases) <= 4096, 'Repository release limit')
    visiting, visited = set(), set()
    def visit(key):
        require(key not in visiting, 'Dependency cycle')
        if key in visited: return
        require(len(visiting) < 64, 'Dependency depth limit')
        visiting.add(key)
        for dep in releases[key]['dependencies']:
            target = (dep['id'],dep['version'])
            require(dep['optional'] or target in releases, 'Missing required dependency release')
            if target in releases: visit(target)
        visiting.remove(key); visited.add(key)
    for key in releases: visit(key)
    return {'projects':len(projects),'supportedAssetTypes':[],'validation':'structure-only'}

def main():
    parser=argparse.ArgumentParser(description=__doc__); commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('validate-repository');p.add_argument('repository',type=Path)
    p=commands.add_parser('build');p.add_argument('pack',type=Path);p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('inspect');p.add_argument('archive',type=Path)
    p=commands.add_parser('build-version');p.add_argument('repository',type=Path);p.add_argument('--manifest',required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='validate-repository': result=validate_repository(args.repository)
        elif args.command in {'build','build-version'}:
            if args.command=='build': manifest,files=load_pack(args.pack)
            else:
                validate_repository(args.repository)
                safe_path(args.manifest);require(re.fullmatch(r'mods/[^/]+/[^/]+/versions/[^/]+/manifest\.json',args.manifest),'Expected repository version manifest')
                manifest=checked(json_bytes(read_file(args.repository,args.manifest,MAX_JSON)),'manifest')
                source=(args.repository/args.manifest).parents[2]/'src'
                files=read_listed_files(args.repository,manifest,source.relative_to(args.repository).as_posix())
            data=build_bytes(manifest,files);write_immutable(args.output,data)
            result={'id':manifest['id'],'version':manifest['version'],'sha256':sha(data),'bytes':len(data),'installable':False,'validation':'structure-only'}
        else:
            require(args.archive.stat().st_size<=MAX_TOTAL,'Archive size limit');manifest,files=inspect_archive(args.archive.read_bytes())
            result={'id':manifest['id'],'version':manifest['version'],'files':len(files),'installable':False,'validation':'structure-only'}
        print(json.dumps(result,sort_keys=True))
    except (Invalid,OSError) as exc: parser.exit(1,str(exc)+'\n')
if __name__=='__main__': main()
