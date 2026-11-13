from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit,urlunsplit,unquote
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import requests,threading,json,hashlib,time,shutil,argparse
parser=argparse.ArgumentParser(description="Collect public EZVIZ overseas static SDK HTML without executing it.")
parser.add_argument("--output",type=Path,default=Path("/tmp/ezviz-doc-discovery-global/sdk-corpus"))
parser.add_argument("--seed-cache",type=Path,default=None,help="Optional directory holding previously fetched public SDK index HTML")
parser.add_argument("--refresh",action="store_true",help="Re-fetch saved HTML rather than reusing it")
args=parser.parse_args()
BASE=args.seed_cache;OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
ORIGIN='https://open.ys7.com';ROOTS={p:f'/doc/en/{p}/' for p in ['android','ios','pc']};seen={};queue=[];local=threading.local();started=time.time()
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,t,attrs):
  for k,v in attrs:
   if (t=='a' and k=='href') or (t in ['frame','iframe'] and k=='src'):
    if v:self.links.append(v)
def canonical(url,source=None):
 p=urlsplit(urljoin(source or ORIGIN,url))
 if p.hostname!='open.ys7.com':return None
 if not any(p.path.startswith(r) for r in ROOTS.values()):return None
 path=p.path
 if path.endswith('/'):path+='index.html'
 if not path.endswith('.html'):return None
 return urlunsplit(('https','open.ys7.com',path,'',''))
def add(url,source):
 url=canonical(url,source)
 if not url:return
 if url in seen:
  if source not in seen[url]['discovered_from']:seen[url]['discovered_from'].append(source)
  return
 if len(seen)>=2500:raise RuntimeError('Safety page cap reached: must not claim closure')
 seen[url]={'url':url,'status':'queued','discovered_from':[source]};queue.append(url)
def outfile(url):return OUT/urlsplit(url).path.removeprefix('/doc/en/')
def session():
 if not hasattr(local,'s'):local.s=requests.Session();local.s.headers.update({'User-Agent':'Mozilla/5.0 (compatible; documentation inventory)'})
 return local.s
def fetch(url):
 p=outfile(url);p.parent.mkdir(parents=True,exist_ok=True)
 if not args.refresh and p.exists() and p.stat().st_size:
  b=p.read_bytes();return {'status':'ok','http_status':200,'final_url':url,'local_path':str(p.relative_to(OUT)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'cache':True},b
 err=None
 for attempt in range(3):
  try:
   r=session().get(url,timeout=(8,18));b=r.content
   if r.status_code!=200:return {'status':'http_error','http_status':r.status_code,'final_url':r.url},None
   if canonical(r.url)!=url:return {'status':'redirect_outside_or_alias','http_status':r.status_code,'final_url':r.url},None
   if b'<html' not in b[:600].lower() and b'<!doctype html' not in b[:600].lower():return {'status':'not_html','http_status':r.status_code,'final_url':r.url},None
   p.write_bytes(b);return {'status':'ok','http_status':r.status_code,'final_url':r.url,'local_path':str(p.relative_to(OUT)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()},b
  except requests.RequestException as e:err=type(e).__name__
 return {'status':'network_error','error':err},None
def save():
 manifest={'collected_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'Follow publicly linked .html pages under /doc/en/android/, /doc/en/ios/, /doc/en/pc/ only. HTML is saved as data and never executed. Query/fragment variants canonicalized.','traversal_finished':not queue and all(x['status']!='queued' for x in seen.values()),'all_discovered_pages_available':all(x['status']=='ok' for x in seen.values()),'known_unavailable_pages':sum(x['status'] not in ['ok','queued'] for x in seen.values()),'limitation':'All same-scope HTML links found in successfully retrieved pages are processed. Unavailable pages may contain undiscoverable links. Assets and non-HTML downloads are outside this corpus.','entries':list(seen.values())}
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
# Optional cache uses only public files and never browser credentials.
if BASE is not None:
 for plat,src,name in [('ios',BASE/'ios.html','index.html'),('pc',BASE/'pc.html','index.html'),('android',BASE/'android-overview.html','overview-summary.html')]:
  if src.exists() and src.stat().st_size:
   dst=OUT/plat/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 for p in (BASE/'sdk-indexes').glob('*.html'):
  plat,name=p.name.split('-',1)
  if p.stat().st_size:
   dst=OUT/plat/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst)
for plat,root in ROOTS.items():add(ORIGIN+root, 'official_overseas_menu_API-Doc')
with ThreadPoolExecutor(max_workers=6) as pool:
 active={};done=0
 while queue or active:
  while queue and len(active)<6:
   u=queue.pop(0);active[pool.submit(fetch,u)]=u
  completed,_=wait(active,return_when=FIRST_COMPLETED)
  for fut in completed:
   u=active.pop(fut);meta,b=fut.result();seen[u].update(meta);done+=1
   if b:
    parser=Links();parser.feed(b.decode('utf-8',errors='replace'))
    for link in parser.links:add(link,u)
   if meta['status']!='ok':print('WARN',u,meta,flush=True)
  save()
  if done%10< len(completed):print('progress',done,'discovered',len(seen),'queued',len(queue),'seconds',round(time.time()-started),flush=True)
save()
from collections import Counter
print('FINAL',dict(Counter(x['status'] for x in seen.values())),dict(Counter(urlsplit(u).path.split('/')[3] for u in seen)),round(time.time()-started),flush=True)
