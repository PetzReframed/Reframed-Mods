import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tooling'))
import catalog as c
import engine_check as engine
from test_catalog import fixture
class Engine(unittest.TestCase):
    def setup_engine(self,directory,repository='PetzReframed/Reframed'):
        commit='a'*40;data=b'synthetic engine artifact, never executed'
        contract={'contractVersion':1,'repository':repository,'sourceCommit':commit,'engineVersion':'git-'+commit,'assetApi':1,'supportedAssetTypes':[],'capabilities':{'validationStatus':'no-runtime-adapters','externalOriginalAssetsRequired':True},'artifacts':[{'path':'petz5reframed-engine.zip','bytes':len(data),'sha256':c.sha(data)}]}
        raw=c.canonical(contract);(directory/'game-build-contract.json').write_bytes(raw);(directory/'petz5reframed-engine.zip').write_bytes(data)
        return commit,c.sha(raw)
    def test_pinned_contract_and_explicit_unsupported(self):
        with tempfile.TemporaryDirectory()as td:
            d=pathlib.Path(td);commit,digest=self.setup_engine(d);checked=engine.verify_engine(d,commit,digest)
            m,f=fixture();package=d/'example.petzmod';package.write_bytes(c.build_bytes(m,f));result=engine.check_pack(checked,package)
            self.assertFalse(result['runtimeCompatible']);self.assertEqual(result['unsupportedAssetTypes'],['music'])
    def test_repository_is_reframed_or_its_former_name(self):
        for repository,accepted in [('PetzReframed/Reframed',True),('PetzReframed/Petz5Reframed',True),('PetzReframed/Other',False)]:
            with tempfile.TemporaryDirectory()as td:
                d=pathlib.Path(td);commit,digest=self.setup_engine(d,repository)
                if accepted:engine.verify_engine(d,commit,digest)
                else:
                    with self.assertRaises(c.Invalid):engine.verify_engine(d,commit,digest)
    def test_tamper_identity_and_artifact(self):
        with tempfile.TemporaryDirectory()as td:
            d=pathlib.Path(td);commit,digest=self.setup_engine(d)
            for wrong_commit,wrong_hash in [('b'*40,digest),(commit,'0'*64)]:
                with self.assertRaises(c.Invalid):engine.verify_engine(d,wrong_commit,wrong_hash)
            (d/'petz5reframed-engine.zip').write_bytes(b'changed')
            with self.assertRaises(c.Invalid):engine.verify_engine(d,commit,digest)
    def test_opt_in_validator_requires_its_own_pin_before_opening_engine_code(self):
        from engine_validator import validate_content
        with tempfile.TemporaryDirectory() as td:
            d=pathlib.Path(td);commit,digest=self.setup_engine(d)
            engine_row=engine.verify_engine(d,commit,digest)
            raw=b'{}';(d/'game-validator-contract.json').write_bytes(raw)
            with self.assertRaisesRegex(c.Invalid,'Validator contract hash'):
                validate_content(engine_row,d,'0'*64,d/'missing.petzmod')
            with self.assertRaisesRegex(c.Invalid,'Unsupported validator contract'):
                validate_content(engine_row,d,c.sha(raw),d/'missing.petzmod')

    def test_incompatible_exact_engine(self):
        with tempfile.TemporaryDirectory()as td:
            d=pathlib.Path(td);commit,digest=self.setup_engine(d);checked=engine.verify_engine(d,commit,digest)
            m,f=fixture();m['compatibility']['engine']='git-'+'b'*40;p=d/'p.petzmod';p.write_bytes(c.build_bytes(m,f))
            with self.assertRaises(c.Invalid):engine.check_pack(checked,p)
if __name__=='__main__':unittest.main()
