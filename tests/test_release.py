import io,json,os,subprocess,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import sys
TOOLING=Path(__file__).resolve().parents[1]/'tooling'
sys.path.insert(0,str(TOOLING))
from release import produce,load_catalog,Committed
C=load_catalog(TOOLING);MANIFEST='mods/test/music/versions/1.0.0/manifest.json'
class Producer(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.repo=self.root/'repo';self.repo.mkdir();self.git('init','-q')
  self.files={'music/test.wav':b'owned inert synthetic bytes','notices/LICENSE.txt':b'CC0 test'}
  self.manifest={'manifestVersion':1,'id':'test.music','version':'1.0.0','name':{'en':'Synthetic'},'description':{'en':'Not playable'},'authors':[{'name':'Test'}],'license':'CC0-1.0','notices':['notices/LICENSE.txt'],'compatibility':{'engine':'*','assetApi':1,'capabilities':[]},'categories':['music'],'dependencies':[],'conflicts':[],'overrides':[],'files':[{'path':p,'bytes':len(b),'sha256':C.sha(b),'type':'notice' if p.startswith('notices/') else 'music',**({} if p.startswith('notices/') else {'target':'test.music:track'})} for p,b in self.files.items()]}
  self.write(MANIFEST,json.dumps(self.manifest,indent=2).encode());self.write('mods/test/music/project.json',C.canonical({k:self.manifest[k] for k in ['id','name','description','authors','categories','license']}))
  for p,b in self.files.items():self.write('mods/test/music/src/'+p,b)
  self.git('add','.');self.git('-c','user.name=Owned Test','-c','user.email=test@example.invalid','commit','-qm','synthetic');self.commit=self.git('rev-parse','HEAD').decode().strip()
 def git(self,*args,input=None):
  p=subprocess.run(['git','-C',str(self.repo),*args],input=input,capture_output=True,check=True,timeout=10);return p.stdout
 def write(self,path,data):
  p=self.repo/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 def run_build(self,name='out',commit=None,path=MANIFEST):return produce(C,self.repo,commit or self.commit,path,self.root/name)
 def test_schema_determinism_actual_embedded_manifest(self):
  a=self.run_build();b=self.run_build('again');self.assertEqual(a,b);C.checked(a,'release');raw=(self.root/'out'/a['package']).read_bytes();self.assertEqual(raw,C.build_bytes(self.manifest,self.files));self.assertEqual(a['sha256'],C.sha(raw))
  with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertEqual(a['manifestSha256'],C.sha(z.read('manifest.json')));self.assertEqual(a['expandedBytes'],sum(i.file_size for i in z.infolist()))
  self.assertNotEqual(a['manifestSha256'],C.sha((self.repo/MANIFEST).read_bytes()))
 def test_pinned_receipt_requires_exact_committed_package_manifest_and_engine(self):
  record=self.run_build();engine='2'*40
  validation={'resultVersion':1,'valid':True,'engineVersion':'git-'+engine,'id':record['id'],'version':record['version'],
              'archiveBytes':record['bytes'],'archiveSha256':record['sha256'],'manifestSha256':record['manifestSha256'],'assetTypes':['music']}
  value={'receiptVersion':1,'sourceRepository':'PetzReframed/Reframed-Mods','sourceCommit':self.commit,'engineCommit':engine,
         'engineContractSha256':'a'*64,'validatorContractSha256':'b'*64,'result':validation}
  path=self.root/'receipt.json'
  def write(obj):
   raw=C.canonical(obj);path.write_bytes(raw);return C.sha(raw)
  def build(name,pin,expected=engine):
   return produce(C,self.repo,self.commit,MANIFEST,self.root/name,receipt=path,expected_receipt_sha256=pin,expected_engine_commit=expected)
  proof=build('validated',write(value));self.assertEqual(proof['validation'],'engine-content');self.assertFalse(proof['installable'])
  self.assertEqual((self.root/'validated/validation-receipt.json').read_bytes(),path.read_bytes())
  for changed,pin,expected in [(value,'0'*64,engine),(value,None,'3'*40),(value|{'sourceCommit':'4'*40},None,engine),
      (value|{'result':validation|{'archiveSha256':'5'*64}},None,engine),(value|{'result':validation|{'manifestSha256':'6'*64}},None,engine)]:
   actual=write(changed)
   with self.assertRaises(ValueError):build('refused',pin or actual,expected)
   self.assertFalse((self.root/'refused').exists())

 def test_dirty_worktree_and_index_do_not_affect_output(self):
  first=self.run_build();self.write(MANIFEST,b'not json');self.write('mods/test/music/src/music/test.wav',b'dirty');self.git('add','.');self.assertEqual(first,self.run_build('dirty'))
 def test_invalid_commit_path_and_identity_leave_no_output(self):
  for commit,path in [('main',MANIFEST),('0'*40,MANIFEST),(self.commit,'../manifest.json'),(self.commit,MANIFEST.replace('1.0.0','2.0.0'))]:
   with self.assertRaises((ValueError,C.Invalid)):self.run_build(commit=commit,path=path)
   self.assertFalse((self.root/'out').exists())
 def test_symlink_entry_rejected_without_following(self):
  oid=self.git('hash-object','-w','--stdin',input=b'/outside/private').decode().strip();self.git('update-index','--cacheinfo','120000,'+oid+',mods/test/music/src/music/test.wav');self.git('-c','user.name=Owned Test','-c','user.email=test@example.invalid','commit','-qm','symlink');commit=self.git('rev-parse','HEAD').decode().strip()
  with self.assertRaisesRegex(ValueError,'Regular blob'):self.run_build(commit=commit)
  self.assertFalse((self.root/'out').exists())
 def test_actual_size_preflight_and_hash_failure_leave_no_output(self):
  with patch.object(C,'MAX_FILE',3):
   with self.assertRaisesRegex(ValueError,'preflight size'):self.run_build()
  self.assertFalse((self.root/'out').exists());self.write('mods/test/music/src/music/test.wav',b'wrong');self.git('add','.');self.git('-c','user.name=Owned Test','-c','user.email=test@example.invalid','commit','-qm','bad hash')
  with self.assertRaises(C.Invalid):self.run_build(commit=self.git('rev-parse','HEAD').decode().strip())
  self.assertFalse((self.root/'out').exists())
 def test_manifest_plus_payload_aggregate_rejects_before_payload_read(self):
  calls=[];original=Committed.blob
  def observed(owner,path,limit):
   calls.append(path)
   if '/src/' in path:raise AssertionError('Payload must not be read')
   return original(owner,path,limit)
  limit=len(C.canonical(self.manifest))+sum(map(len,self.files.values()))-1
  with patch.object(C,'MAX_TOTAL',limit),patch.object(Committed,'blob',observed):
   with self.assertRaisesRegex(ValueError,'before payload reads'):self.run_build()
  self.assertEqual(calls,['mods/test/music/project.json',MANIFEST]);self.assertFalse((self.root/'out').exists())
 def test_existing_output_never_overwritten_and_isolated_cli(self):
  record=self.run_build();before=(self.root/'out/release.json').read_bytes()
  with self.assertRaises(FileExistsError):self.run_build()
  self.assertEqual(before,(self.root/'out/release.json').read_bytes())
  import sys
  p=subprocess.run([sys.executable,'-I',str(TOOLING/'release.py'),'--trusted-tooling',str(TOOLING),'--repository',str(self.repo),'--commit',self.commit,'--manifest',MANIFEST,'--out',str(self.root/'cli')],capture_output=True,check=True,timeout=20);self.assertEqual(json.loads(p.stdout),record)
if __name__=='__main__':unittest.main()
