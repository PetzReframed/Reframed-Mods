import copy, io, json, pathlib, stat, sys, tempfile, unittest, zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tooling'))
import catalog as c

def fixture():
    files={'assets/music/example.wav':b'authored synthetic fixture; not playable audio', 'notices/LICENSE.txt':b'Synthetic test author grants CC0.'}
    manifest={'manifestVersion':1,'id':'test.example','version':'1.0.0','name':{'en':'Synthetic'},'description':{'en':'Test only, no runtime support'},'authors':[{'name':'Test author'}],'license':'CC0-1.0','notices':['notices/LICENSE.txt'],'compatibility':{'engine':'*','assetApi':1,'capabilities':[]},'categories':['music'],'dependencies':[],'conflicts':[],'overrides':[],'files':[{'path':p,'bytes':len(v),'sha256':c.sha(v),'type':'notice' if p.startswith('notices/') else 'music','target':'test.example:'+('notice' if p.startswith('notices/') else 'track')}for p,v in files.items()]}
    for row in manifest['files']:
        if row['type']=='notice':row.pop('target')
    return manifest,files

class Contract(unittest.TestCase):
    def test_deterministic_bytes_and_roundtrip(self):
        m,f=fixture();a=c.build_bytes(m,f);b=c.build_bytes(dict(reversed(list(m.items()))),dict(reversed(list(f.items()))));self.assertEqual(a,b)
        self.assertEqual(c.inspect_archive(a),(m,f))
        with zipfile.ZipFile(io.BytesIO(a))as z:
            self.assertEqual(z.namelist(),sorted(z.namelist()));self.assertTrue(all(i.date_time==(1980,1,1,0,0,0) and i.compress_type==0 for i in z.infolist()))
    def test_original_inputs_unchanged(self):
        m,f=fixture();old=copy.deepcopy((m,f));c.build_bytes(m,f);self.assertEqual((m,f),old)
    def test_hash_size_unknown_key_and_boolean_integer_reject(self):
        for change in [lambda m:m['files'][0].update(sha256='0'*64),lambda m:m['files'][0].update(bytes=1),lambda m:m.update(script='run.js'),lambda m:m.update(manifestVersion=True)]:
            m,f=fixture();change(m)
            with self.assertRaises(c.Invalid):c.build_bytes(m,f)
    def test_paths(self):
        for p in ['../x','/x','C:/x','a\\b','a//b','a/./b','a/CON.txt','a/trailing.','a/x:y','a/é']:
            with self.subTest(path=p),self.assertRaises(c.Invalid):c.safe_path(p)
    def test_unlisted_and_missing_notices(self):
        m,f=fixture();f['other.txt']=b'x'
        with self.assertRaises(c.Invalid):c.build_bytes(m,f)
        m,f=fixture();m['notices']=['missing.txt']
        with self.assertRaises(c.Invalid):c.build_bytes(m,f)
    def test_case_alias_and_targets(self):
        for target in ['other.namespace:x','test.example:track']:
            m,f=fixture();m['files'][1]['target']=target
            with self.assertRaises(c.Invalid):c.build_bytes(m,f)
        m,f=fixture();row=copy.deepcopy(m['files'][0]);row['path']=row['path'].upper();row['target']='test.example:second';m['files'].append(row);f[row['path']]=f['assets/music/example.wav']
        with self.assertRaises(c.Invalid):c.build_bytes(m,f)
    def test_executable_and_lfs_reject(self):
        for path,data in [('assets/music/evil.js',b'alert(1)'),('assets/music/raw.wav',b'version https://git-lfs.github.com/spec/v1\noid sha256:abc')]:
            m,f=fixture();old=m['files'][0]['path'];del f[old];f[path]=data;m['files'][0].update(path=path,bytes=len(data),sha256=c.sha(data))
            with self.assertRaises(c.Invalid):c.build_bytes(m,f)
    def test_no_runtime_capability_or_override_claim(self):
        for key,value in [('overrides',['stock:room']),('capabilities',['new-toy'])]:
            m,f=fixture();(m['compatibility'] if key=='capabilities' else m)[key]=value
            with self.assertRaises(c.Invalid):c.build_bytes(m,f)
    def test_malformed_archive_profiles(self):
        for name,method,mode in [('../x',0,stat.S_IFREG),('manifest.json',zipfile.ZIP_DEFLATED,stat.S_IFREG),('manifest.json',0,stat.S_IFLNK)]:
            b=io.BytesIO()
            with zipfile.ZipFile(b,'w')as z:
                i=zipfile.ZipInfo(name);i.compress_type=method;i.create_system=3;i.external_attr=mode<<16;z.writestr(i,b'{}')
            with self.assertRaises(c.Invalid):c.inspect_archive(b.getvalue())
    def test_duplicate_json_and_nonfinite(self):
        for data in [b'{"a":1,"a":2}',b'{"a":NaN}',b'\xff']:
            with self.assertRaises(c.Invalid):c.json_bytes(data)
    def test_immutable_output(self):
        with tempfile.TemporaryDirectory()as d:
            path=pathlib.Path(d)/'one.petzmod';c.write_immutable(path,b'first');c.write_immutable(path,b'first')
            with self.assertRaises(c.Invalid):c.write_immutable(path,b'second')
            self.assertEqual(path.read_bytes(),b'first')
    def test_total_declared_bound_precedes_payload_reads(self):
        m,f=fixture();old=c.MAX_TOTAL
        try:
            c.MAX_TOTAL=1
            with self.assertRaisesRegex(c.Invalid,'before reads'):c.read_listed_files(pathlib.Path('does-not-exist'),m)
        finally:c.MAX_TOTAL=old
    def test_limits_before_archive_extraction(self):
        m,f=fixture();a=c.build_bytes(m,f);old=c.MAX_TOTAL
        try:
            c.MAX_TOTAL=10
            with self.assertRaises(c.Invalid):c.inspect_archive(a)
        finally:c.MAX_TOTAL=old
    def test_repository_release_build_and_dependency_cycles(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);(root/'catalog/v1').mkdir(parents=True)
            (root/'catalog/v1/index.json').write_bytes(c.canonical({'catalogVersion':1,'supportedAssetTypes':[],'projects':[]}))
            def add_pack(slug,dependency=None):
                m,f=fixture();m['id']='test.'+slug
                for row in m['files']:
                    if 'target' in row:row['target']=m['id']+':'+row['target'].split(':')[1]
                if dependency:m['dependencies']=[{'id':'test.'+dependency,'version':'1.0.0','optional':False}]
                base=root/'mods/test'/slug;(base/'versions/1.0.0').mkdir(parents=True,exist_ok=True)
                for path,data in f.items():
                    out=base/'src'/path;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data)
                (base/'project.json').write_bytes(c.canonical({k:m[k]for k in ['id','name','description','authors','categories','license']}))
                (base/'versions/1.0.0/manifest.json').write_bytes(c.canonical(m))
                return m,f
            m,f=add_pack('one');self.assertEqual(c.validate_repository(root)['projects'],1)
            import subprocess
            output=root/'built.petzmod'
            run=subprocess.run([sys.executable,'-I',str(c.ROOT/'tooling/catalog.py'),'build-version',str(root),'--manifest','mods/test/one/versions/1.0.0/manifest.json','--output',str(output)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(c.inspect_archive(output.read_bytes()),(m,f))
            add_pack('one','missing')
            with self.assertRaisesRegex(c.Invalid,'Missing required'):c.validate_repository(root)
            add_pack('one','two');add_pack('two','one')
            with self.assertRaisesRegex(c.Invalid,'cycle'):c.validate_repository(root)
    def test_src_symlink_outside_repository_is_rejected(self):
        import os
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as external:
            root=pathlib.Path(td);outside=pathlib.Path(external);m,f=fixture()
            for name,data in f.items():
                p=outside/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            (root/'mods/test/example').mkdir(parents=True)
            link=root/'mods/test/example/src'
            try:os.symlink(outside,link,target_is_directory=True)
            except OSError:self.skipTest('Symlink privilege unavailable; Linux CI covers this boundary')
            with self.assertRaisesRegex(c.Invalid,'Links are forbidden'):c.read_listed_files(root,m,'mods/test/example/src')
    def test_metadata_has_no_runtime_target(self):
        m,f=fixture();self.assertNotIn('target',m['files'][1]);c.build_bytes(m,f)
        m['files'][1]['target']='test.example:notice'
        with self.assertRaisesRegex(c.Invalid,'Metadata'):c.build_bytes(m,f)
        m,f=fixture();m['files'][0].pop('target')
        with self.assertRaises(c.Invalid):c.build_bytes(m,f)
    def test_disguised_nested_zip(self):
        m,f=fixture();b=io.BytesIO()
        with zipfile.ZipFile(b,'w')as z:z.writestr('nested.txt','x')
        path=m['files'][0]['path'];f[path]=b.getvalue();m['files'][0].update(bytes=len(f[path]),sha256=c.sha(f[path]))
        with self.assertRaisesRegex(c.Invalid,'Nested ZIP'):c.build_bytes(m,f)
    def test_empty_catalog(self):
        self.assertEqual(c.validate_repository(c.ROOT)['supportedAssetTypes'],[])
    def test_unknown_schema_keyword_fails_closed(self):
        with self.assertRaises(c.Invalid):c.validate_schema({}, {'oneOf':[]})
    def test_all_shipped_schema_examples(self):
        m,f=fixture();c.checked(m,'manifest')
        project={k:m[k]for k in ['id','name','description','authors','categories','license']};c.checked(project,'project')
        c.checked({'catalogVersion':1,'supportedAssetTypes':[],'projects':[]},'catalog')
        record={'project':project,'releases':[]};c.checked(record,'project-record')
if __name__=='__main__':unittest.main()
