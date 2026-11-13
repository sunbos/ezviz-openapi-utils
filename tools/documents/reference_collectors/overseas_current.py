from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from urllib.parse import urlencode
import requests,threading,json,hashlib,time
BASE=Path('/tmp/ezviz-doc-discovery-global');OUT=BASE/'en-current-pages';RAW=OUT/'raw';RAW.mkdir(parents=True,exist_ok=True)
source_manifest=BASE/'en-menu-manifest.json';rows=json.loads(source_manifest.read_text());docs=[r for r in rows if r.get('id') is not None and not r.get('href')];tls=threading.local()
def utc():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sess():
 if not hasattr(tls,'s'):
  tls.s=requests.Session();tls.s.headers.update({'User-Agent':'Mozilla/5.0 (compatible; public documentation inventory)'})
 return tls.s
def digest(b):return hashlib.sha256(b).hexdigest()
def get(row):
 ident=str(row['id']);url='https://open.ys7.com/help/api/help_doc/doc/list?'+urlencode({'pageStart':1,'pageSize':1,'tag':1,'docId':ident});result={'doc_id':ident,'title':row['path'][-1],'category_path':row['path'],'source_page_url':'https://open.ys7.com/help/en/'+ident,'request_url':url,'request_method':'GET','requested_at_utc':utc(),'metadata_source':'fresh_http_response','status':'pending','html_content_sha256':None,'raw_file':None,'attempts':[]}
 for attempt in range(1,4):
  started=utc()
  try:
   response=sess().get(url,timeout=(8,25));b=response.content;raw_name=ident+'.json';(RAW/raw_name).write_bytes(b)
   result['attempts'].append({'attempt':attempt,'started_at_utc':started,'finished_at_utc':utc(),'http_status':response.status_code})
   result.update({'fetched_at_utc':utc(),'http_status':response.status_code,'final_url':response.url,'content_type':response.headers.get('Content-Type'),'etag':response.headers.get('ETag'),'last_modified':response.headers.get('Last-Modified'),'raw_file':'raw/'+raw_name,'raw_bytes':len(b),'raw_sha256':digest(b)})
   if response.status_code!=200:result['status']='http_error';return result
   try:data=response.json()
   except ValueError:result['status']='invalid_json';return result
   result['meta_code']=data.get('meta',{}).get('code');result['source_total']=data.get('data',{}).get('total');items=data.get('data',{}).get('list')
   if str(result['meta_code'])!='200':result['status']='source_error';return result
   if items==[] and result['source_total']==0:result['status']='source_missing';return result
   if not isinstance(items,list) or len(items)!=1:result['status']='unexpected_response_shape';return result
   doc=items[0];result.update({'returned_doc_id':str(doc.get('docId')),'platform_type':doc.get('platformType'),'source_tag':doc.get('tag'),'source_title':doc.get('fileName'),'source_updated_at':doc.get('updateTime')})
   if str(doc.get('docId'))!=ident or doc.get('platformType')!='doc_open_en' or doc.get('tag')!=1:result['status']='source_mismatch';return result
   content=doc.get('htmlContent')
   if not isinstance(content,str) or not content.strip():result['status']='source_empty_content';return result
   result.update({'status':'ok','html_content_chars':len(content),'html_content_bytes':len(content.encode('utf-8')),'html_content_sha256':digest(content.encode('utf-8'))});return result
  except requests.RequestException as e:
   result['attempts'].append({'attempt':attempt,'started_at_utc':started,'finished_at_utc':utc(),'error_type':type(e).__name__})
 result['status']='network_error';result['finished_at_utc']=utc();return result
results=[];start=utc()
def save():
 counts={}
 for r in results:counts[r['status']]=counts.get(r['status'],0)+1
 m={'started_at_utc':start,'updated_at_utc':utc(),'menu_source_file':str(source_manifest),'menu_source_sha256':digest(source_manifest.read_bytes()),'expected_unique_doc_ids':51,'request_semantics':'Exact official English UI GET with pageStart=1, pageSize=1, tag=1, docId. No untagged fallback. Fresh responses only.','counts':counts,'completed':len(results)==len(docs),'entries':sorted(results,key=lambda r:int(r['doc_id']))}
 (OUT/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
assert len(docs)==len({str(r['id']) for r in docs})==51
with ThreadPoolExecutor(max_workers=4) as pool:
 futures=[pool.submit(get,r) for r in docs]
 for future in as_completed(futures):
  r=future.result();results.append(r);save();print(len(results),r['doc_id'],r['status'],r.get('html_content_chars'),flush=True)
save();print('DONE',len(results),flush=True)
