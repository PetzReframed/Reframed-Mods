import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tooling'))
import catalog as c
import engine_check as engine
from test_catalog import fixture
class Engine(unittest.TestCase):
    def setup_engine(self,directory):
        commit='a'*40;data=b'synthetic engine artifact, never executed'
        contract={'contractVersion':1,'repository':'PetzReframed/Petz5Reframed','sourceCommit':commit,'engineVersion':'git-'+commit,'assetApi':1,'supportedAssetTypes':[],'capabilities':{'validationStatus':'no-runtime-adapters','externalOriginalAssetsRequired':True},'artifacts':[{'path':'petz5reframed-engine.zip','bytes':len(data),'sha256':c.sha(data)}]}
        raw=c.canonical(contract);(directory/'game-build-contract.json').write_bytes(raw);(directory/'petz5reframed-engine.zip').write_bytes(data)
        return commit,c.sha(raw)
    def test_pinned_contract_and_explicit_unsupported(self):
        with tempfile.TemporaryDirectory()as td:
            d=pathlib.Path(td);commit,digest=self.setup_engine(d);checked=engine.verify_engine(d,commit,digest)
            m,f=fixture();package=d/'example.petzmod';package.write_bytes(c.build_bytes(m,f));result=engine.check_pack(checked,package)
            self.assertFalse(result['runtimeCompatible']);self.assertEqual(result['unsupportedAssetTypes'],['music'])
    def test_tamper_identity_and_artifact(self):
        with tempfile.TemporaryDirectory()as td:
            d=pathlib.Path(td);commit,digest=self.setup_engine(d)
            for wrong_commit,wrong_hash in [('b'*40,digest),(commit,'0'*64)]:
                with self.assertRaises(c.Invalid):engine.verify_engine(d,wrong_commit,wrong_hash)
            (d/'petz5reframed-engine.zip').write_bytes(b'changed')
            with self.assertRaises(c.Invalid):engine.verify_engine(d,commit,digest)
    def test_incompatible_exact_engine(self):
        with tempfile.TemporaryDirectory()as td:
            d=pathlib.Path(td);commit,digest=self.setup_engine(d);checked=engine.verify_engine(d,commit,digest)
            m,f=fixture();m['compatibility']['engine']='git-'+'b'*40;p=d/'p.petzmod';p.write_bytes(c.build_bytes(m,f))
            with self.assertRaises(c.Invalid):engine.check_pack(checked,p)
if __name__=='__main__':unittest.main()
