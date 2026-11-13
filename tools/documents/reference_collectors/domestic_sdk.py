from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter
import requests, threading, json, hashlib, time, argparse

ap = argparse.ArgumentParser(description='Archive publicly linked Chinese EZVIZ static SDK HTML without executing it')
ap.add_argument('--output', type=Path, default=Path('/tmp/ezviz-doc-discovery-cn/sdk-corpus'))
ap.add_argument('--seeds', type=Path, default=Path('/tmp/ezviz-doc-discovery-cn/sdk-seeds.json'))
ap.add_argument('--workers', type=int, default=6)
ap.add_argument('--refresh', action='store_true')
args = ap.parse_args()
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
SEEDS = json.loads(args.seeds.read_text())
ROOTS = sorted({urlsplit(x['url']).path.rsplit('/',1)[0]+'/' for x in SEEDS})
seen, queue, outgoing = {}, [], {}
local = threading.local()
started = time.time()
previous = {}
if (OUT/'manifest.json').exists():
    previous = {x['url']:x for x in json.loads((OUT/'manifest.json').read_text())['entries']}

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.assets=[]; self.title=[]; self.in_title=False
    def handle_starttag(self, tag, attrs):
        if tag=='title': self.in_title=True
        for key,val in attrs:
            if not val: continue
            if (tag=='a' and key=='href') or (tag in ('frame','iframe') and key=='src'): self.links.append(val)
            elif (tag in ('img','script') and key=='src') or (tag=='link' and key=='href'): self.assets.append(val)
    def handle_endtag(self, tag):
        if tag=='title': self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title.append(data)

def canonical(url, source=None):
    p=urlsplit(urljoin(source or 'https://open.ys7.com',url))
    if p.hostname!='open.ys7.com' or not any(p.path.startswith(r) for r in ROOTS):return None
    path=p.path+'index.html' if p.path.endswith('/') else p.path
    if not path.endswith('.html'):return None
    return urlunsplit(('https','open.ys7.com',path,'',''))

def add(url,source):
    u=canonical(url,source)
    if not u:return
    if u in seen:
        if source not in seen[u]['discovered_from']:seen[u]['discovered_from'].append(source)
        return
    if len(seen)>=2500:raise RuntimeError('Page cap reached; closure is not established')
    seen[u]={'url':u,'status':'queued','discovered_from':[source]};queue.append(u)

def outfile(url):
    path=unquote(urlsplit(url).path.removeprefix('/doc/zh/'))
    p=(OUT/path).resolve()
    if not p.is_relative_to(OUT.resolve()):raise ValueError('Path escapes output')
    return p

def fetch(url):
    p=outfile(url);p.parent.mkdir(parents=True,exist_ok=True)
    old=previous.get(url,{})
    if not args.refresh and old.get('status')=='ok' and p.exists():
        b=p.read_bytes()
        if hashlib.sha256(b).hexdigest()==old.get('sha256'):
            return {k:v for k,v in old.items() if k not in ('discovered_from','url')},b
    if not hasattr(local,'session'):
        local.session=requests.Session()
        local.session.headers.update({'User-Agent':'Mozilla/5.0 (compatible; public documentation archive)'})
    attempts=[]
    for attempt in range(3):
        at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        try:
            r=local.session.get(url,timeout=(8,18));b=r.content
            attempts.append({'at':at,'http_status':r.status_code})
            base={'attempts':attempts,'http_status':r.status_code,'final_url':r.url,'retrieved_at_utc':at,'content_type':r.headers.get('Content-Type'),'etag':r.headers.get('ETag'),'last_modified':r.headers.get('Last-Modified')}
            if r.status_code!=200:
                if r.status_code in (429,500,502,503,504) and attempt<2:time.sleep(attempt+1);continue
                return dict(base,status='http_error'),None
            if canonical(r.url)!=url:return dict(base,status='redirect_outside_or_alias'),None
            if b'<html' not in b[:1000].lower() and b'<!doctype html' not in b[:1000].lower():return dict(base,status='not_html'),None
            parsed=Links();parsed.feed(b.decode('utf-8',errors='replace'))
            if not parsed.title:return dict(base,status='missing_html_title'),None
            temp=p.with_suffix('.tmp');temp.write_bytes(b);temp.replace(p)
            return dict(base,status='ok',local_path=str(p.relative_to(OUT)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),title=''.join(parsed.title)),b
        except requests.RequestException as e:attempts.append({'at':at,'error':type(e).__name__})
    return {'status':'network_error','attempts':attempts},None

def save():
    entries=list(seen.values())
    failures=[x for x in entries if x['status'] not in ('ok','queued')]
    manifest={'started_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(started)),'updated_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope_roots':ROOTS,'seeds':SEEDS,'traversal_finished':not queue and all(x['status']!='queued' for x in entries),'all_discovered_pages_available':all(x['status']=='ok' for x in entries),'status_counts':dict(Counter(x['status'] for x in entries)),'limitation':'Closure covers same-root HTML href/frame links found in successfully retrieved pages. Unavailable pages may hide further links. Linked assets, SDK binaries and other roots are inventoried but not downloaded. Saved HTML is inert data and was not executed. HTTP variants normalized to HTTPS; query/fragment variants canonicalized.','entries':entries}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (OUT/'missing.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2)+'\n')
    (OUT/'outgoing-links.json').write_text(json.dumps(list(outgoing.values()),ensure_ascii=False,indent=2)+'\n')

for seed in SEEDS:add(seed['url'],seed['source'])
with ThreadPoolExecutor(max_workers=args.workers) as pool:
    active={};done=0
    while queue or active:
        while queue and len(active)<args.workers:
            u=queue.pop(0);active[pool.submit(fetch,u)]=u
        completed,_=wait(active,return_when=FIRST_COMPLETED)
        for future in completed:
            u=active.pop(future);meta,b=future.result();seen[u].update(meta);done+=1
            if b:
                parser=Links();parser.feed(b.decode('utf-8',errors='replace'))
                for link in parser.links:
                    if canonical(link,u):add(link,u)
                    else:
                        target=urljoin(u,link)
                        if target not in outgoing:outgoing[target]={'url':target,'kind':'href','discovered_from':[]}
                        if u not in outgoing[target]['discovered_from']:outgoing[target]['discovered_from'].append(u)
                for link in parser.assets:
                    target=urljoin(u,link)
                    if target not in outgoing:outgoing[target]={'url':target,'kind':'asset','discovered_from':[]}
                    if u not in outgoing[target]['discovered_from']:outgoing[target]['discovered_from'].append(u)
            if meta['status']!='ok':print('WARN',u,meta['status'],flush=True)
        save()
        if done%10<len(completed):print('progress',done,'discovered',len(seen),'queued',len(queue),'seconds',round(time.time()-started),flush=True)
save()
print('FINAL',dict(Counter(x['status'] for x in seen.values())),'seconds',round(time.time()-started),flush=True)
