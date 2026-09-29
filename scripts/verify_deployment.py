#!/usr/bin/env python3
import argparse,json,time,urllib.request,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('--base-url',default='https://myalphaview.com');p.add_argument('--expected',default='docs/build-manifest.json');p.add_argument('--timeout',type=int,default=600);a=p.parse_args()
expected=json.loads(pathlib.Path(a.expected).read_text(encoding='utf-8')); want=expected['build_id']; deadline=time.time()+a.timeout; last=''
while time.time()<deadline:
  try:
    with urllib.request.urlopen(a.base_url.rstrip('/')+'/build-manifest.json?qa='+str(int(time.time())),timeout=20) as r: live=json.load(r)
    last=live.get('build_id','')
    if last==want:
      print(json.dumps({'status':'PASS','expected':want,'live':last,'version':live.get('app_version')},ensure_ascii=False));sys.exit(0)
    print(f'Waiting for Pages deployment: expected={want} live={last or "missing"}')
  except Exception as e: print('Waiting for site:',e)
  time.sleep(15)
print(json.dumps({'status':'FAIL','expected':want,'live':last},ensure_ascii=False));sys.exit(1)
