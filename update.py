"""Fixed-rule job refresh. No model/API key; sources and failures remain visible.

Run: python update.py [--sources all|external|employers]
Writes a public snapshot for GitHub Pages; no account credential is required.
Never treat source content as executable instructions.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode
from urllib.robotparser import RobotFileParser
import threading
import time
from dateutil import parser as dateparser
import requests
from bs4 import BeautifulSoup
import model

ROOT=Path(__file__).resolve().parent
CONFIG=json.loads((ROOT/"config.json").read_text())
CACHE=ROOT/"cache"; CACHE.mkdir(exist_ok=True)
OUTPUT=ROOT/"output"; OUTPUT.mkdir(exist_ok=True)
NOW=datetime.now(timezone.utc).isoformat()
UA="HKCareerWatch/1.0 (personal weekly job discovery; public pages only)"
HK=re.compile(r"hong\s*kong|hongkong|香港|\bHK\b",re.I)
EARLY=re.compile(r"\bintern(?:ship)?s?\b|\btrainee\b|\bgraduate\b|\bplacement\b|\bsummer analyst\b|\bco[ -]?op\b|\bapprentice\b|實習|实习|管培|見習|见习|應屆|应届",re.I)

def clean(s):
    s=str(s or "")
    if "<" in s:s=BeautifulSoup(s,"html.parser").get_text(" ",strip=True)
    return re.sub(r"\s+"," ",s).strip()
def norm(s): return model.norm(s)
def canonical_company(s):
    return model.company(s)
def canonical_url(url):
    return model.canonical_url(url)
def iso_date(s):
    if not s or str(s).lower() in ("nan","nat","none"):return None
    m=re.match(r"(\d{4}-\d{2}-\d{2})",str(s))
    if m:
        try:datetime.strptime(m[1],"%Y-%m-%d");return m[1]
        except ValueError:return None
    if re.search(r"\b\d{4}\b",str(s)) and re.search(r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec",str(s),re.I):
        try:return dateparser.parse(str(s)).date().isoformat()
        except (ValueError,OverflowError):pass
    return None
def categorize(title,description=""):
    result=model.classify(title,description,'Hong Kong',now=NOW)
    return None if result['state']=='excluded' else result['category']

def make_job(company,title,url,location,source,origin,posted=None,deadline=None,description="",note="",hk_context=False):
    job=model.make(company,clean(title).replace('🆕','').strip(),url,location,source,origin,iso_date(posted),iso_date(deadline),description,note,now=NOW)
    # Keep relevant rejected candidates for a transparent audit, not every worldwide ATS vacancy.
    if job and (model.hit('intern',job['title']) or model.hit('graduate',job['title']) or job['role_tags'] or job['state']!='excluded'):return job
    return None

_robots={};_robotlock=threading.Lock()
def allowed(url):
    host=urlparse(url).netloc
    with _robotlock:
        known=_robots.get(host)
    if known is not None:return known.can_fetch(UA,url) if isinstance(known,RobotFileParser) else known
    try:
        rr=requests.get(f"https://{host}/robots.txt",headers={"User-Agent":UA},timeout=10)
        if rr.status_code==200:
            rp=RobotFileParser();rp.parse(rr.text.splitlines());rule=rp
        elif rr.status_code in (401,403,429):rule=False
        else:rule=True
    except requests.RequestException:rule=True
    with _robotlock:_robots[host]=rule
    return rule.can_fetch(UA,url) if isinstance(rule,RobotFileParser) else rule

def fetch(url,check_robots=True):
    if check_robots and not allowed(url):raise RuntimeError("robots.txt 不允许自动读取")
    key=sha256(url.encode()).hexdigest();path=CACHE/(key+".json")
    old=json.loads(path.read_text()) if path.exists() else {}
    headers={"User-Agent":UA}
    if old.get("etag"):headers["If-None-Match"]=old["etag"]
    if old.get("modified"):headers["If-Modified-Since"]=old["modified"]
    for attempt in range(3):
        r=requests.get(url,headers=headers,timeout=(10,22))
        if r.status_code not in (429,500,502,503,504) or attempt==2:break
        retry=r.headers.get('Retry-After','')
        time.sleep(min(30,int(retry)) if retry.isdigit() else 2**attempt)
    if r.status_code==304 and old.get("body"):return old["body"],old.get("url",url),True
    r.raise_for_status()
    if len(r.content)>6_000_000:raise RuntimeError("页面超过采集大小限制")
    body=r.text
    path.write_text(json.dumps({"etag":r.headers.get("ETag"),"modified":r.headers.get("Last-Modified"),"body":body,"url":r.url}),encoding="utf-8")
    return body,r.url,body==old.get("body")

def status(id,name,url,state,message,jobs):return {"id":id,"name":name,"url":url,"status":state,"message":message,"jobs":len(jobs),"checked_at":NOW}
def json_jobs(obj):
    if isinstance(obj,list):
        for v in obj:yield from json_jobs(v)
    if isinstance(obj,dict):
        if obj.get("@type")=="JobPosting" or "JobPosting" in (obj.get("@type") if isinstance(obj.get("@type"),list) else []):yield obj
        for k in ("@graph","itemListElement","item"):
            if k in obj:yield from json_jobs(obj[k])

def parse_page(body,url,company,origin="employer",source="雇主官网",hk_context=False):
    soup=BeautifulSoup(body,"html.parser");jobs=[]
    for script in soup.select('script[type="application/ld+json"]'):
        try:objs=list(json_jobs(json.loads(script.get_text())))
        except (ValueError,TypeError):continue
        for obj in objs:
            location=json.dumps(obj.get("jobLocation",obj.get("applicantLocationRequirements",{})),ensure_ascii=False)
            title=obj.get("title",obj.get("name",""));org=obj.get("hiringOrganization",{})
            name=company if origin=="employer" else org.get("name",company) if isinstance(org,dict) else company
            job=make_job(name,title,obj.get("url") or url,location,source,origin,obj.get("datePosted"),obj.get("validThrough"),obj.get("description",""),hk_context=hk_context)
            if job:jobs.append(job)
    def prop(key):
        node=soup.select_one(f'[itemprop="{key}"]')
        return node.get("content",node.get_text(" ",strip=True)) if node else ""
    if not jobs and prop("title"):
        location=" ".join(prop(k) for k in ("addressCountry","addressLocality","addressRegion"))
        if not location.strip():
            # SuccessFactors exposes a job-specific labelled country instead of microdata.
            labelled=re.search(r'Country/Region:\s*([A-Z]{2})\b',soup.get_text(' ',strip=True))
            if labelled:location='Hong Kong' if labelled[1]=='HK' else labelled[1]
        description=prop("description")
        context=soup.select_one(".job")
        detail=clean(context.get_text(" ",strip=True)) if context else description
        job=make_job(company,prop("title"),url,location,source,origin,prop("datePosted"),prop("validThrough"),description, hk_context=hk_context)
        if job:
            # HSBC dates describe actual programme timing; summer is explicit in June/July starts of short internships.
            start=re.search(r"Programme Start Date and Duration:\s*(.+?)\s*Opening Date:",detail)
            if start:job['timing']['start']=start[1][:420]
            jobs.append(job)
    if not jobs and "lvmh.com" in urlparse(url).netloc and re.search(r"/our-job-offers/[A-Z0-9]+",url):
        h=soup.find("h1");txt=clean(soup.get_text(" ",strip=True))
        if h:txt=txt[txt.find(clean(h.get_text())):]
        pub=re.search(r"Published on\s*:?\s*(\d{2})[./](\d{2})[./](\d{4})",txt,re.I)
        posted=f"{pub[3]}-{pub[2]}-{pub[1]}" if pub else None
        loc=re.search(r'Place of employment\s*:\s*(.+?)(?:Contrat type|Contract type|Required experience)',txt,re.I)
        deadline=re.search(r'Application Deadline:\s*(\d{1,2}\s+[A-Za-z]+\s+20\d{2})',txt,re.I)
        job=make_job(company,clean(h.get_text()) if h else "",url,loc[1] if loc else '',source,origin,posted,deadline[1] if deadline else None,description=txt)
        if job:jobs.append(job)
    return jobs,soup

def workopia():
    url="https://raw.githubusercontent.com/workopia/Hong-Kong-Graduate-Internship-Jobs/main/README.md"
    try:
        body,_,unchanged=fetch(url,False);soup=BeautifulSoup(body,"html.parser");jobs=[]
        rows=soup.select("tbody tr")
        if not rows:raise RuntimeError("香港清单结构发生变化，未读取到岗位行")
        last_company=''
        for tr in rows:
            cells=tr.find_all("td")
            if len(cells)<6:continue
            company,title,loc=[clean(c.get_text(" ",strip=True)) for c in cells[:3]]
            if company in ('↳','↪','〃',''):company=last_company
            else:last_company=company
            link=cells[5].find("a",href=True)
            if not link:continue
            job=make_job(company,title,link["href"],loc,"Workopia","external",description=clean(cells[4]),note="发现线索，申请前请核对原始岗位页。")
            if job:jobs.append(job)
        return jobs,status("workopia","Workopia 香港清单",url,"unchanged" if unchanged else "ok",f"读取 {len(rows)} 条，筛选保留 {len(jobs)} 条；未用相对年龄推算发布日期。",jobs)
    except Exception as e:return [],status("workopia","Workopia 香港清单",url,"error",str(e)[:220],[])

def jobspy_query(site,query):
    from jobspy import scrape_jobs
    cfg=CONFIG["jobspy"];jobs=[]
    # JobSpy may log errors and return an empty dataframe. Preserve those failures.
    errors=[]
    class Capture(logging.Handler):
        def emit(self,record):
            if record.levelno>=logging.ERROR:errors.append(record.getMessage())
    worker=threading.get_ident()
    handler=Capture();handler.addFilter(lambda record:record.thread==worker);logger=logging.getLogger("JobSpy");logger.addHandler(handler)
    try:
        frame=scrape_jobs(site_name=[site],search_term=query,location=cfg["location"],country_indeed=cfg["country_indeed"],results_wanted=100,hours_old=336,verbose=1,linkedin_fetch_description=True)
        records=json.loads(frame.to_json(orient="records",date_format="iso"))
        for row in records:
            desc=row.get("description") or ""
            job=make_job(row.get("company"),row.get("title"),row.get("job_url_direct") or row.get("job_url"),row.get("location") or "",f"JobSpy · {site}","external",row.get("date_posted"),description=desc,note="发现线索，申请前请核对原始岗位页。")
            if job:jobs.append(job)
        state="error" if errors else "partial" if len(records)>=100 else "ok" if records else "empty"
        msg=f"{query}：读取 {len(records)} 条，保留 {len(jobs)} 条。"+("达到 100 条上限，可能截断。" if len(records)>=100 else '')+("；"+" / ".join(errors)[:180] if errors else "")
        return jobs,status(f"jobspy:{site}:{query}",f"JobSpy · {site}","https://github.com/speedyapply/JobSpy",state,msg,jobs)
    except Exception as e:return [],status(f"jobspy:{site}:{query}",f"JobSpy · {site}","https://github.com/speedyapply/JobSpy","error",str(e)[:220],[])
    finally:logger.removeHandler(handler)

def lever(company,url):
    slug=urlparse(url).path.strip("/").split("/")[0]
    if not slug:return []
    body,_,_=fetch(f"https://api.lever.co/v0/postings/{slug}?mode=json",False);jobs=[]
    for row in json.loads(body):
        cat=row.get("categories",{})
        desc=row.get('descriptionPlain','')+' '+ ' '.join(clean(x.get('content','')) for x in row.get('lists',[]))
        job=make_job(company,row.get("text"),row.get("hostedUrl"),cat.get("location",""),"雇主官网 · Lever","employer",description=desc)
        if job:jobs.append(job)
    return jobs

def workday(company,url):
    p=urlparse(url);tenant=p.netloc.split(".")[0];parts=p.path.strip("/").split("/");board=parts[1] if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}",parts[0]) and len(parts)>1 else parts[0]
    if not board:return []
    endpoint=f"https://{p.netloc}/wday/cxs/{tenant}/{board}/jobs"
    jobs=[]
    facets={k:[v] for k,v in parse_qsl(p.query) if k in ("jobFamilyGroup","workerSubType","locationCountry")}
    for offset in range(0,200,20):
        r=requests.post(endpoint,json={"appliedFacets":facets,"limit":20,"offset":offset,"searchText":"Hong Kong"},headers={"User-Agent":UA},timeout=20);r.raise_for_status();result=r.json()
        for row in result.get("jobPostings",[]):
            if not EARLY.search(row.get('title','')) and not any(re.search(r['pattern'],row.get('title',''),re.I) for r in model.RULES['directions'].values()):continue
            detail_url=f"https://{p.netloc}/wday/cxs/{tenant}/{board}"+row["externalPath"]
            detail=requests.get(detail_url,headers={"User-Agent":UA},timeout=20)
            detail.raise_for_status()
            d=detail.json().get("jobPostingInfo",{})
            loc=d.get("location",row.get("locationsText",""))
            if d.get("additionalLocations"):loc+=" "+" ".join(d["additionalLocations"])
            job=make_job(company,d.get("title",row["title"]),f"https://{p.netloc}/{board}"+row["externalPath"],loc,"雇主官网 · Workday","employer",d.get("startDate"),d.get("endDate"),d.get("jobDescription",""))
            if job:jobs.append(job)
        if offset+20>=result.get("total",0):break
    if result.get('total',0)>200:raise RuntimeError('Workday 超过 200 条分页上限，不能确认完整覆盖')
    return jobs

def greenhouse(company,url):
    p=urlparse(url);parts=p.path.strip('/').split('/')
    board=dict(parse_qsl(p.query)).get('for') or parts[0]
    body,_,_=fetch(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true',False)
    result=[]
    for row in json.loads(body).get('jobs',[]):
        j=make_job(company,row['title'],row['absolute_url'],row.get('location',{}).get('name',''),'雇主官网 · Greenhouse','employer',description=row.get('content',''))
        if j:result.append(j)
    return result

def smartrecruiters(company,url):
    board=urlparse(url).path.strip('/').split('/')[0];jobs=[]
    for offset in range(0,2000,100):
        body,_,_=fetch(f'https://api.smartrecruiters.com/v1/companies/{board}/postings?limit=100&offset={offset}',False)
        data=json.loads(body)
        for row in data.get('content',[]):
            loc=row.get('location',{})
            if not HK.search(json.dumps(loc)):continue
            detail,_,_=fetch(f"https://api.smartrecruiters.com/v1/companies/{board}/postings/{row['id']}",False)
            d=json.loads(detail);sections=d.get('jobAd',{}).get('sections',{})
            desc=' '.join(s.get('text','') for key,s in sections.items() if key!='companyDescription')
            j=make_job(company,d['name'],d.get('applyUrl') or f"https://jobs.smartrecruiters.com/{board}/{row['id']}",json.dumps(loc),'雇主官网 · SmartRecruiters','employer',d.get('releasedDate'),description=desc)
            if j:jobs.append(j)
        if offset+100>=data.get('totalFound',0):return jobs
    raise RuntimeError('SmartRecruiters 达到分页上限，覆盖不完整')

def freehire():
    cfg=model.RULES['freehire'];jobs=[];errors=[];count=0;partial=False
    for query in cfg['queries']:
        try:
            for page in range(cfg['max_pages']):
                params={'countries':'HK','limit':cfg['page_size'],'offset':page*cfg['page_size'],**query}
                url=cfg['base_url']+'/agent/jobs/search?'+urlencode(params)
                body,_,_=fetch(url,False);data=json.loads(body)
                if data.get('ignored_params') or data.get('meta',{}).get('ignored_params'):raise ValueError('API 忽略请求参数 '+str(data.get('ignored_params') or data['meta']['ignored_params']))
                rows=data.get('jobs',data.get('data',[]))
                if not isinstance(rows,list):raise ValueError('FreeHire 返回结构变化')
                count+=len(rows)
                for row in rows:
                    j=make_job(row.get('company'),row.get('title'),row.get('url'),row.get('location',''),'FreeHire · '+row.get('source','ATS'),'external',row.get('posted_at'),description=row.get('description',''),note='FreeHire 完整职位说明；地点和岗位类型由本站再次核对。')
                    if j:
                        # A third party's closed_at is a review signal, not an official closure.
                        if row.get('closed_at') and j['state'] not in ('excluded','archived'):
                            j['state']='review';j['review_reasons'].append('FreeHire 标记关闭，待官网确认')
                        jobs.append(j)
                total=data.get('total',data.get('meta',{}).get('total'))
                if not rows or len(rows)<cfg['page_size'] or (isinstance(total,int) and (page+1)*cfg['page_size']>=total):break
            else:partial=True
        except Exception as e:errors.append(str(query)+': '+str(e)[:140])
    state='error' if len(errors)==len(cfg['queries']) else 'partial' if errors or partial else 'ok'
    message=f'双路径 {len(cfg["queries"])} 组查询，读取 {count} 条（跨查询可重复）。'
    if partial:message+=' 达到分页上限，可能截断。'
    if errors:message+=' '+ '；'.join(errors)[:600]
    return jobs,status('freehire','FreeHire 完整 ATS 职位',cfg['base_url']+'/agent/jobs/search',state,message,jobs)

def official_detail(seed):
    """Known official links supplement discovery; they do not expand the 97-company watchlist."""
    url=seed['url'];sid='watch:'+sha256(url.encode()).hexdigest()[:12]
    try:
        p=urlparse(url)
        if 'myworkdayjobs.com' in p.netloc and '/job/' in p.path:
            parts=p.path.strip('/').split('/');board=parts[1] if re.fullmatch(r'[a-z]{2}-[A-Z]{2}',parts[0]) else parts[0]
            external='/job/'+p.path.split('/job/',1)[1]
            api=f'https://{p.netloc}/wday/cxs/{p.netloc.split(".")[0]}/{board}'+external
            body,_,_=fetch(api,False);d=json.loads(body)['jobPostingInfo']
            j=make_job(seed['company'],d['title'],url,d.get('location',''),'雇主官网 · Workday','employer',d.get('startDate'),d.get('endDate'),d.get('jobDescription',''))
            if not j:raise ValueError('岗位未满足基础字段')
            jobs=[j]
        else:
            body,final,_=fetch(url);jobs,soup=parse_page(body,final,seed['company'])
            if not jobs:
                for node in soup.select('nav,footer,script,style'):node.decompose()
                txt=clean(soup.get_text(' ',strip=True));heading=soup.select_one(seed.get('selector','h1'))
                title=clean(heading.get_text()) if heading else ''
                if not title or not EARLY.search(title):raise ValueError('官方页缺少可解析的具体岗位标题；保留旧线索')
                loc=re.search(seed.get('location_pattern',r'Location\s*:\s*([^.;]{2,100})'),txt,re.I)
                location=loc[1] if loc else ''
                if location=='HKG':location='Hong Kong'
                deadline=re.search(r'(?:application deadline|application closing date)\s*:\s*(\d{1,2}\s+[A-Za-z]+\s+20\d{2})',txt,re.I)
                j=make_job(seed['company'],title,final,location,'雇主官网 · 已知岗位','employer',deadline=deadline[1] if deadline else None,description=txt)
                if not j:raise ValueError('官方页无法形成岗位记录')
                jobs=[j]
            for j in jobs:
                if seed.get('summer_evidence') and seed['summer_evidence'] in j['title']:
                    j['category']='holiday';j['season']='summer';j['timing']['start']=seed['summer_evidence']+'（原文未注明年份）'
                    if not j['project_years']:
                        j['state']='review';j['review_reasons'].append('明确夏季时段，但项目年份未注明')
        return jobs,status(sid,seed['company']+' · 已知官方岗位',url,'ok','已读取具体官方职位；不代表该公司全量覆盖。',jobs)
    except Exception as e:return [],status(sid,seed['company']+' · 已知官方岗位',url,'error',str(e)[:220],[])

def employer(emp):
    jobs=[];errors=[];unchanged=True;pages=0;structured=0
    urls=[emp["url"]]+[w["url"] for w in CONFIG["watch_urls"] if canonical_company(w["company"])==emp["name"]]
    prior=OUTPUT/"snapshot.json"
    if prior.exists():
        # Follow discovered direct employer links on later runs, bounded per employer.
        for j in json.loads(prior.read_text()).get("jobs",[]):
            if j.get('state') in ('excluded','archived','expired'):continue
            host=urlparse(j["url"]).netloc
            ownhost=urlparse(emp["url"]).netloc.removeprefix("www.").removeprefix("careers.").removeprefix("jobs.")
            if canonical_company(j["company"])==emp["name"] and (host==ownhost or host.endswith("."+ownhost)):
                urls.append(j["url"])
    seen=set();ats_seen=set()
    for url in list(dict.fromkeys(urls)):
        if url in seen:continue
        seen.add(url)
        try:
            body,final,same=fetch(url);unchanged=unchanged and same;pages+=1
            found,soup=parse_page(body,final,emp["name"]);jobs.extend(found);structured+=len(found)
            ats_urls=[final]+[urljoin(final,a["href"]) for a in soup.select("a[href]") if re.search(r"jobs\.lever\.co|myworkdayjobs\.com|greenhouse\.io|smartrecruiters\.com",a["href"])]+re.findall(r'https?://[^\s"<>\x27]+myworkdayjobs[^\s"<>\x27]*',body)
            for ats in ats_urls[:5]:
                host=urlparse(ats).netloc
                if host in ats_seen:continue
                if "jobs.lever.co" in host:ats_seen.add(host);jobs.extend(lever(emp["name"],ats));structured+=1
                elif "myworkdayjobs.com" in host:ats_seen.add(host);jobs.extend(workday(emp["name"],ats));structured+=1
                elif 'greenhouse.io' in host:ats_seen.add(host);jobs.extend(greenhouse(emp['name'],ats));structured+=1
                elif 'smartrecruiters.com' in host:ats_seen.add(host);jobs.extend(smartrecruiters(emp['name'],ats));structured+=1
            candidates=[]
            for a in soup.select("a[href]"):
                title=clean(a.get_text(" ",strip=True));link=urljoin(final,a["href"])
                if categorize(title) and len(title)>12 and link.startswith("https://") and link not in seen and not re.search(r"linkedin.com|facebook.com|youtube.com|mailto:",link):
                    candidates.append((title,link))
            for title,link in candidates[:5]:
                seen.add(link)
                try:
                    child,childurl,_=fetch(link);pages+=1
                    found,childsoup=parse_page(child,childurl,emp["name"]);jobs.extend(found);structured+=len(found)
                    # Without JobPosting schema, only specific HK job pages qualify.
                    heading=childsoup.find("h1");heading=clean(heading.get_text()) if heading else title
                    txt=clean(childsoup.get_text(" ",strip=True))
                    if not found and re.search(r"/job/|/jobs/[^/?]+|jobdetail|vacancy/",childurl,re.I):
                        loc=re.search(r'(?:job location|location\s*:|based in)\s*([^.;]{2,100})',txt,re.I)
                        job=make_job(emp["name"],heading,childurl,loc[1] if loc else '',"雇主官网","employer",description=txt[:15000],note="官网未提供结构化字段；缺少地点或时间证据时列为待核实。")
                        if job:jobs.append(job)
                except Exception as e:errors.append(str(e))
        except Exception as e:errors.append(str(e))
    state="partial" if pages else "error"
    msg=f"已检查 {pages} 个页面，找到 {len(jobs)} 条；有限范围检查，未覆盖全部招聘列表。"
    if not pages:msg="；".join(errors)[:220] or "无法获取招聘页"
    elif errors:msg+=' 部分页面未能访问：'+'；'.join(errors)[:250]
    return jobs,status(emp["id"],emp["name"],emp["url"],state,msg,jobs)

def merge(records):
    return model.merge(records)

def retain_history(previous, current, sources, now,profile='full'):
    return model.retain(previous,current,sources,now,profile)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--profile',choices=['light','full'],default='full')
    ap.add_argument("--sources",choices=["all","external","employers","watch"],default="all")
    ap.add_argument("--previous",default=str(ROOT/"jobs.json"))
    ap.add_argument("--output",default=str(ROOT/"jobs.json"))
    args=ap.parse_args()
    previous=json.loads(Path(args.previous).read_text()) if Path(args.previous).exists() else {}
    # Reuse previously discovered official URLs without contacting the old Site.
    (OUTPUT/"snapshot.json").write_text(json.dumps(previous,ensure_ascii=False),encoding="utf-8")
    alljobs=[];sources=[]
    tasks=[]
    if args.sources in ("all","external"):
        tasks.append((workopia,()))
        tasks.append((freehire,()))
        if args.profile=='full':tasks += [(jobspy_query,(site,q)) for site in CONFIG["jobspy"]["sites"] for q in model.RULES['jobspy_queries']]
    if args.profile=='full' and args.sources in ("all","employers"):
        tasks +=[(employer,(emp,)) for emp in CONFIG["employers"]]
    if args.profile=='full' and args.sources in ('all','employers','watch'):
        tasks +=[(official_detail,(seed,)) for seed in json.loads((ROOT/'official-watch.json').read_text())]
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map={pool.submit(fn,*a):(getattr(fn,'__name__','source'),a) for fn,a in tasks}
        for future in as_completed(future_map):
            try:
                jobs,st=future.result();alljobs+=jobs;sources.append(st)
                print(json.dumps({"source":st["name"],"status":st["status"],"jobs":len(jobs)},ensure_ascii=False),flush=True)
            except Exception as e:
                print(json.dumps({"unexpected_error":str(e)}),file=sys.stderr)
    if len(sources)!=len(tasks):
        print("Incomplete collection: unexpected task failure; previous public snapshot preserved",file=sys.stderr)
        return 2
    errors=sum(s["status"] in ("error","blocked") for s in sources)
    if not sources or errors==len(sources):
        (OUTPUT/'last-failure.json').write_text(json.dumps({'attempted_at':NOW,'profile':args.profile,'sources':sources},ensure_ascii=False,indent=2))
        print("All sources failed; previous public snapshot preserved",file=sys.stderr)
        return 2
    snapshot=retain_history(previous,alljobs,sources,NOW,args.profile if args.sources=='all' else 'manual')
    path=Path(args.output)
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(path)
    report={"jobs":len(snapshot["jobs"]),"sources":len(sources),"failed_sources":errors,"file":str(path)}
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0

if __name__=="__main__":sys.exit(main())
