"""Trusted committed-blob release producer; structural output only, never publication."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,re,subprocess

def load_catalog(tooling):
    path=Path(tooling).resolve()/'catalog.py'
    spec=importlib.util.spec_from_file_location('trusted_mod_catalog',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class Committed:
    def __init__(self,repo,commit):
        if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Explicit lowercase 40-hex commit required')
        self.repo=Path(repo).resolve();self.commit=commit
        if self.git('cat-file','-t',commit).strip()!=b'commit':raise ValueError('Source is not a commit')
    def git(self,*args):
        env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')};env['GIT_NO_LAZY_FETCH']='1';env['GIT_TERMINAL_PROMPT']='0'
        p=subprocess.run(['git','--no-replace-objects','--literal-pathspecs','-C',str(self.repo),*args],capture_output=True,env=env,timeout=20)
        if p.returncode:raise ValueError('Committed Git object unavailable: '+p.stderr.decode('utf-8',errors='replace')[:500])
        return p.stdout
    def blob(self,path,limit):
        parts=path.split('/')
        if not parts or any(not p or p in ('.','..') for p in parts) or '\\' in path or '\0' in path:raise ValueError('Invalid committed path')
        for i in range(1,len(parts)+1):
            prefix='/'.join(parts[:i]);raw=self.git('ls-tree','-z','--full-tree',self.commit,'--',prefix)
            rows=raw.rstrip(b'\0').split(b'\0')
            if len(rows)!=1 or b'\t' not in rows[0]:raise ValueError('Missing exact tree entry')
            header,name=rows[0].split(b'\t',1);mode,kind,oid=header.split()
            if name.decode('utf-8')!=prefix:raise ValueError('Unexpected tree entry')
            if i<len(parts):
                if mode!=b'040000' or kind!=b'tree':raise ValueError('Non-directory path ancestor')
            elif mode not in (b'100644',b'100755') or kind!=b'blob':raise ValueError('Regular blob required')
        size=int(self.git('cat-file','-s',oid.decode()).strip())
        if size>limit:raise ValueError('Committed blob exceeds preflight size bound')
        data=self.git('cat-file','blob',oid.decode())
        if len(data)!=size:raise ValueError('Committed blob size changed')
        return data

def checked_receipt(c,receipt,path_sha,engine_commit,commit,manifest,record):
    if not (isinstance(path_sha,str) and re.fullmatch('[a-f0-9]{64}',path_sha) and
            isinstance(engine_commit,str) and re.fullmatch('[a-f0-9]{40}',engine_commit)):
        raise ValueError('Trusted receipt SHA-256 and engine commit are required')
    path=Path(receipt)
    raw=c.read_file(path.parent,path.name,16384)
    if c.sha(raw)!=path_sha:raise ValueError('Validation receipt hash mismatch')
    value=c.json_bytes(raw)
    pins={k:value.get(k) for k in ('engineContractSha256','validatorContractSha256')}
    if not all(isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in pins.values()):
        raise ValueError('Missing validated contract pins')
    expected={'receiptVersion':1,'sourceRepository':'PetzReframed/Reframed-Mods','sourceCommit':commit,
              'engineCommit':engine_commit,**pins,'result':{'resultVersion':1,'valid':True,'engineVersion':'git-'+engine_commit,
              'id':record['id'],'version':record['version'],'archiveBytes':record['bytes'],'archiveSha256':record['sha256'],
              'manifestSha256':record['manifestSha256'],'assetTypes':sorted({r['type'] for r in manifest['files']}-{'preview','notice'})}}
    if c.canonical(value)!=c.canonical(expected) or manifest['compatibility']['engine'] not in ('*','git-'+engine_commit):
        raise ValueError('Validation receipt differs from committed package or pinned engine')
    return raw,{'receiptSha256':path_sha,'engineCommit':engine_commit,**pins}


def produce(catalog,repo,commit,manifest_path,output,*,receipt=None,expected_receipt_sha256=None,expected_engine_commit=None):
    c=catalog;path=c.safe_path(manifest_path);parts=path.split('/')
    if len(parts)!=6 or parts[0]!='mods' or parts[3]!='versions' or parts[5]!='manifest.json':raise ValueError('Expected mods/publisher/slug/versions/version/manifest.json')
    source=Committed(repo,commit);base='/'.join(parts[:3]);project=c.checked(c.json_bytes(source.blob(base+'/project.json',c.MAX_JSON)),'project')
    manifest=c.checked(c.json_bytes(source.blob(path,c.MAX_JSON)),'manifest')
    if project['id']!=parts[1]+'.'+parts[2] or manifest['id']!=project['id'] or manifest['version']!=parts[4]:raise ValueError('Project/path/manifest identity mismatch')
    declared=sum(r['bytes'] for r in manifest['files']);embedded=c.canonical(manifest)
    if len(embedded)+declared>c.MAX_TOTAL:raise ValueError('Expanded size limit before payload reads')
    files={}
    for row in manifest['files']:
        name=c.safe_path(row['path']);data=source.blob(base+'/src/'+name,min(row['bytes'],c.MAX_FILE));files[name]=data
    archive=c.build_bytes(manifest,files);expanded=len(embedded)+sum(map(len,files.values()))
    if expanded>c.MAX_TOTAL:raise ValueError('Expanded archive size limit')
    digest=c.sha(archive)
    record={'id':manifest['id'],'version':manifest['version'],'package':'packages/'+digest+'.petzmod','sha256':digest,'bytes':len(archive),'expandedBytes':expanded,'manifestSha256':c.sha(embedded),'sourceCommit':commit,'installable':False,'validation':'structure-only','unsupportedReason':'No runtime asset adapters are released.'}
    receipt_bytes=None
    if any(v is not None for v in (receipt,expected_receipt_sha256,expected_engine_commit)):
        if receipt is None:raise ValueError('A validation receipt is required with its pins')
        receipt_bytes,proof=checked_receipt(c,receipt,expected_receipt_sha256,expected_engine_commit,commit,manifest,record)
        record.update(validation='engine-content',unsupportedReason='Content validated for one pinned engine. Catalog publication has not been approved.',engineValidation=proof)
    c.checked(record,'release')
    out=Path(output);out.mkdir() # exclusive: no existing directory/output is ever reused
    (out/'packages').mkdir()
    with (out/record['package']).open('xb') as stream:stream.write(archive)
    with (out/'release.json').open('xb') as stream:stream.write(c.canonical(record))
    if receipt_bytes is not None:(out/'validation-receipt.json').write_bytes(receipt_bytes)
    return record

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trusted-tooling',type=Path,required=True);p.add_argument('--repository',type=Path,required=True);p.add_argument('--commit',required=True);p.add_argument('--manifest',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--validation-receipt',type=Path);p.add_argument('--expected-receipt-sha256');p.add_argument('--expected-engine-commit');a=p.parse_args()
    print(json.dumps(produce(load_catalog(a.trusted_tooling),a.repository,a.commit,a.manifest,a.out,receipt=a.validation_receipt,expected_receipt_sha256=a.expected_receipt_sha256,expected_engine_commit=a.expected_engine_commit),sort_keys=True))
if __name__=='__main__':main()
