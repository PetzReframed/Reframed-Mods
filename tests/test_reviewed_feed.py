import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tooling'))
import catalog as c
from reviewed_feed import check_closure, generate
from release import produce
import test_release


class ReviewedFeed(unittest.TestCase):
    def setUp(self):
        fixture = test_release.Producer()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.f = fixture
        self.engine = '2'*40
        project = {k:fixture.manifest[k] for k in ['id','name','description','authors','categories','license']}
        self.path = 'mods/test/second/versions/1.0.0/manifest.json'
        manifest = fixture.manifest | {'id':'test.second','dependencies':[{'id':'test.music','version':'1.0.0','optional':False}],
                                      'files':[dict(row) for row in fixture.manifest['files']]}
        for row in manifest['files']:
            if 'target' in row:
                row['target']='test.second:track'
        fixture.write(self.path,c.canonical(manifest))
        fixture.write('mods/test/second/project.json',c.canonical(project|{'id':'test.second'}))
        for name,data in fixture.files.items():
            fixture.write('mods/test/second/src/'+name,data)
        fixture.git('add','.')
        fixture.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','second')
        self.commit=fixture.git('rev-parse','HEAD').decode().strip()

    def pin(self,path):
        # Synthetic trusted receipt fixture. The engine checker tests exercise receipt creation.
        f=self.f; work=f.root/('review-'+path.split('/')[2])
        row=produce(c,f.repo,self.commit,path,work)
        result={'resultVersion':1,'valid':True,'engineVersion':'git-'+self.engine,'id':row['id'],'version':row['version'],
                'archiveBytes':row['bytes'],'archiveSha256':row['sha256'],'manifestSha256':row['manifestSha256'],'assetTypes':['music']}
        raw=c.canonical({'receiptVersion':1,'sourceRepository':'PetzReframed/Petz5Reframed-Mods','sourceCommit':self.commit,
                         'engineCommit':self.engine,'engineContractSha256':'a'*64,'validatorContractSha256':'b'*64,'result':result})
        receipt=work/'review.json';receipt.write_bytes(raw)
        return path,receipt,c.sha(raw)

    def test_reviewed_feed_binds_immutable_archives_exact_engine_and_required_dependencies(self):
        base=self.pin(test_release.MANIFEST);other=self.pin(self.path)
        out=self.f.root/'catalog'
        with self.assertRaisesRegex(c.Invalid,'Missing reviewed dependency'):
            generate(self.f.repo,self.commit,self.engine,[other],out)
        with self.assertRaisesRegex(ValueError,'receipt hash'):
            generate(self.f.repo,self.commit,self.engine,[(base[0],base[1],'0'*64)],out)
        with self.assertRaisesRegex(ValueError,'pinned engine'):
            generate(self.f.repo,self.commit,'3'*40,[base],out)
        self.assertFalse(out.exists())
        only=self.f.root/'single'
        generate(self.f.repo,self.commit,self.engine,[base],only)
        self.assertFalse((only/'projects/test.second.json').exists())
        index=generate(self.f.repo,self.commit,self.engine,[other,base],out)
        self.assertEqual(index,json.loads((out/'index.json').read_bytes()))
        self.assertEqual(index['supportedAssetTypes'],['music'])
        self.assertEqual([p['id'] for p in index['projects']],['test.music','test.second'])
        for entry in index['projects']:
            record=json.loads((out/entry['record']).read_bytes());row,=record['releases']
            self.assertEqual(row['id'],entry['id']);self.assertTrue(row['installable'])
            self.assertEqual(row['validation'],'engine-adapters');self.assertEqual(row['compatibility']['engine'],'git-'+self.engine)
            self.assertEqual(row['sourceCommit'],self.commit);self.assertEqual(row['types'],['music'])
            data=(out/row['package']).read_bytes();self.assertEqual(c.sha(data),row['sha256'])
            self.assertEqual(len(data),row['bytes']);manifest,_=c.inspect_archive(data)
            self.assertEqual(row['dependencies'],manifest['dependencies']);self.assertEqual(row['conflicts'],manifest['conflicts'])
            self.assertEqual(manifest['compatibility']['engine'],'*')
            self.assertEqual(c.sha(c.canonical(manifest)),row['manifestSha256'])
            self.assertEqual(json.loads((out/'evidence'/(row['sha256']+'.json')).read_bytes())['result']['archiveSha256'],row['sha256'])

    def test_reviewed_closure_checks_room_targets_conflicts_and_optional_versions(self):
        base=('one.pack','1.0.0');top=('two.pack','1.0.0')
        rows={k:{'files':[{'type':'playscenes','target':k[0]+':garden'}],'dependencies':[],'conflicts':[]} for k in (base,top)}
        check_closure(base,rows);check_closure(top,rows)
        rows[top]['dependencies']=[{'id':base[0],'version':base[1],'optional':False}]
        with self.assertRaisesRegex(c.Invalid,'Playscene name collision'):check_closure(top,rows)
        rows[base]['files']=[]
        rows[base]['conflicts']=[top[0]]
        with self.assertRaisesRegex(c.Invalid,'Conflicting'):check_closure(top,rows)
        rows[base]['conflicts']=[]
        rows[base]['dependencies']=[{'id':top[0],'version':'2.0.0','optional':True}]
        with self.assertRaisesRegex(c.Invalid,'Incompatible selected dependency'):check_closure(top,rows)


if __name__=='__main__':unittest.main()
