"""Verify an explicitly pinned engine artifact; report unsupported packs honestly."""
import argparse,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from catalog import Invalid,require,json_bytes,sha,read_file,inspect_archive,MAX_TOTAL

def verify_engine(directory,expected_commit,expected_contract_sha):
    require(re.fullmatch('[0-9a-f]{40}',expected_commit) and re.fullmatch('[0-9a-f]{64}',expected_contract_sha),'Trusted expected commit and contract hash required')
    raw=read_file(Path(directory),'game-build-contract.json',1024*1024)
    require(sha(raw)==expected_contract_sha,'Engine contract hash mismatch')
    value=json_bytes(raw)
    require(set(value)=={'contractVersion','repository','sourceCommit','engineVersion','assetApi','supportedAssetTypes','capabilities','artifacts'},'Unexpected engine contract fields')
    require(type(value['contractVersion'])is int and value['contractVersion']==1 and type(value['assetApi'])is int and value['assetApi']==1,'Unsupported engine validation interface')
    require(value['repository']=='PetzReframed/Petz5Reframed' and value['sourceCommit']==expected_commit and value['engineVersion']=='git-'+expected_commit,'Engine identity mismatch')
    require(isinstance(value['capabilities'],dict) and type(value['capabilities'].get('externalOriginalAssetsRequired'))is bool,'Invalid capability types')
    require(value['supportedAssetTypes']==[] and value['capabilities']=={'validationStatus':'no-runtime-adapters','externalOriginalAssetsRequired':True},'Unsupported capability contract; consumer upgrade required')
    require(isinstance(value['artifacts'],list) and len(value['artifacts'])==1,'Exactly one engine artifact required')
    row=value['artifacts'][0]
    require(set(row)=={'path','bytes','sha256'} and row['path']=='petz5reframed-engine.zip','Unexpected engine artifact')
    require(type(row['bytes'])is int and 0<row['bytes']<=MAX_TOTAL,'Engine artifact size bound')
    data=read_file(Path(directory),row['path'],MAX_TOTAL)
    require(len(data)==row['bytes'] and sha(data)==row['sha256'],'Engine artifact bytes mismatch')
    return value

def check_pack(engine,package):
    require(package.stat().st_size<=MAX_TOTAL,'Package size limit')
    manifest,_=inspect_archive(package.read_bytes())
    require(manifest['compatibility']['engine'] in ('*',engine['engineVersion']),'Pack requires a different engine build')
    types=sorted({r['type']for r in manifest['files']} - {'preview','notice'})
    unsupported=sorted(set(types)-set(engine['supportedAssetTypes']))
    return {'pack':manifest['id'],'version':manifest['version'],'engineCommit':engine['sourceCommit'],'structurallyValid':True,'runtimeCompatible':False,'unsupportedAssetTypes':unsupported,'reason':'No runtime asset adapters are released.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',type=Path,required=True);p.add_argument('--expected-commit',required=True);p.add_argument('--expected-contract-sha256',required=True);p.add_argument('--package',type=Path,required=True);a=p.parse_args()
    try:
        engine=verify_engine(a.engine,a.expected_commit,a.expected_contract_sha256);result=check_pack(engine,a.package);print(json.dumps(result,sort_keys=True));raise SystemExit(2)
    except(Invalid,OSError)as exc:p.exit(1,str(exc)+'\n')
if __name__=='__main__':main()
