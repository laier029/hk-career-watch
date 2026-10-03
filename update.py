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
import unicodedata
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
from urllib.robotparser import RobotFileParser
import threading
from dateutil import parser as dateparser
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
CONFIG=json.loads((ROOT/"config.json").read_text())
CACHE=ROOT/"cache"; CACHE.mkdir(exist_ok=True)
OUTPUT=ROOT/"output"; OUTPUT.mkdir(exist_ok=True)
NOW=datetime.now(timezone.utc).isoformat()
UA="HKCareerWatch/1.0 (personal weekly job discovery; public pages only)"
HK=re.compile(r"hong\s*kong|hongkong|香港|\bHK\b",re.I)
EARLY=re.compile(r"\bintern(?:ship)?s?\b|\btrainee\b|\bgraduate\b|\bplacement\b|\bsummer analyst\b|\bco[ -]?op\b|\bapprentice\b|實習|实习|管培|見習|见习|應屆|应届",re.I)
BUSINESS=re.compile(r"supply|logistic|procure|purchas|planning|inventory|operations?|commercial|business|analyst|analytics|data|finance|financial|banking|investment|markets?|trading|quant|research|consult|strategy|strategic|risk|compliance|sales|retail|brand|marketing|merchand|sourc|product|management|graduate programme|graduate program|internship program|winter internship|summer internship|供应|供應|物流|采购|採購|运营|營運|分析|金融|财务|財務|管理|策略|商业|商業",re.I)
EXCLUDE=re.compile(r"\b(senior|principal|director|lead|head of|vice president|VP|nurse|doctor|clinical|software engineer|software develop|frontend|backend|full.stack|mechanical engineer|civil engineer)\b|\bexperience day\b|\bcareer fair\b",re.I)
SUMMER=re.compile(r"summer|暑期|暑假",re.I)
GRAD=re.compile(r"\bgraduate\b|\bmanagement trainee\b|\btrainee\b|\bfull.time analyst\b|管培|畢業|毕业|應屆|应届",re.I)

def clean(s):
    s=str(s or "")
    if "<" in s:s=BeautifulSoup(s,"html.parser").get_text(" ",strip=True)
    return re.sub(r"\s+"," ",s).strip()
def norm(s): return re.sub(r"[^a-z0-9\u4e00-\u9fff]","",unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower())
def canonical_company(s):
    n=norm(s)
    for emp in CONFIG["employers"]:
        if any(n==norm(a) or (len(norm(a))>=5 and n.startswith(norm(a))) for a in emp["aliases"]):
            return emp["name"]
    return s
def canonical_url(url):
    p=urlparse(url);q=[(k,v) for k,v in parse_qsl(p.query) if not k.startswith("utm_") and k not in ("trk","trackingId","refId")]
    return urlunparse((p.scheme,p.netloc,p.path,"",urlencode(q),""))
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
    if EXCLUDE.search(title):return None
    if not EARLY.search(title) and not EARLY.search(description[:1800]):return None
    if not BUSINESS.search(title) and not BUSINESS.search(description[:1800]):
        if not re.fullmatch(r"(?:\d{4}\s+)?(?:winter |summer |student )?intern(?:ship)?(?: programme| program)?(?: \d{4})?",title,re.I):return None
    if SUMMER.search(title):return "summer"
    if re.search(r"intern|placement|co[ -]?op|實習|实习",title,re.I):
        # Descriptions may mention a later graduate offer; never classify by that mention.
        if SUMMER.search(description[:400]):return "summer"
        return "daily"
    return "graduate" if GRAD.search(title+" "+description[:800]) else "daily"

def make_job(company,title,url,location,source,origin,posted=None,deadline=None,description="",note="",hk_context=False):
    title=clean(title).replace("🆕","").strip();company=clean(company)
    category=categorize(title,clean(description))
    if not category or not company or not url or not str(url).startswith(("https://","http://")):return None
    if not HK.search(clean(location)) and not hk_context:return None
    if category=="summer" and re.search(r"\b202[0-6]\b",title):return None
    if category=="graduate" and re.search(r"\b202[0-6]\b",title):return None
    company=canonical_company(company)
    url=canonical_url(url)
    if category=="graduate" and re.search(r"\b2027\b",title):note=(note+" 2027 届项目，需核对毕业时间与入职要求。").strip()
    posted,deadline=iso_date(posted),iso_date(deadline)
    if posted and posted>datetime.now(timezone.utc).date().isoformat():posted=None
    key=sha256((norm(company)+"|"+norm(title)).encode()).hexdigest()[:24]
    return {"id":key,"company":company,"title":title,"category":category,"origin":origin,"posted":posted,"deadline":deadline,"url":url,"source":source,"note":note,"location":clean(location) or "Hong Kong","first_seen":NOW,"state":"active"}

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
    r=requests.get(url,headers=headers,timeout=(10,22))
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
        description=prop("description")
        context=soup.select_one(".job")
        detail=clean(context.get_text(" ",strip=True)) if context else description
        job=make_job(company,prop("title"),url,location,source,origin,prop("datePosted"),prop("validThrough"),description, hk_context=hk_context)
        if job:
            # HSBC dates describe actual programme timing; summer is explicit in June/July starts of short internships.
            start=re.search(r"Programme Start Date and Duration:\s*(.+?)\s*Opening Date:",detail)
            if job["category"]=="daily" and start and re.search(r"(?:Jun|Jul).*?2027.*?(?:weeks|2 months|3 months)",start[1],re.I):job["category"]="summer"
            jobs.append(job)
    if not jobs and "lvmh.com" in urlparse(url).netloc and re.search(r"/our-job-offers/[A-Z0-9]+",url):
        h=soup.find("h1");txt=clean(soup.get_text(" ",strip=True));pub=re.search(r"Published on\s*:?\s*(\d{2})[./](\d{2})[./](\d{4})",txt,re.I)
        posted=f"{pub[3]}-{pub[2]}-{pub[1]}" if pub else None
        job=make_job(company,clean(h.get_text()) if h else "",url,"Hong Kong" if HK.search(txt) else "",source,origin,posted,description=txt)
        if job:jobs.append(job)
    return jobs,soup

def workopia():
    url="https://raw.githubusercontent.com/workopia/Hong-Kong-Graduate-Internship-Jobs/main/README.md"
    try:
        body,_,unchanged=fetch(url,False);soup=BeautifulSoup(body,"html.parser");jobs=[]
        rows=soup.select("tbody tr")
        if not rows:raise RuntimeError("香港清单结构发生变化，未读取到岗位行")
        for tr in rows:
            cells=tr.find_all("td")
            if len(cells)<6:continue
            company,title,loc=[clean(c.get_text(" ",strip=True)) for c in cells[:3]]
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
    handler=Capture();logger=logging.getLogger("JobSpy");logger.addHandler(handler)
    try:
        frame=scrape_jobs(site_name=[site],search_term=query,location=cfg["location"],country_indeed=cfg["country_indeed"],results_wanted=cfg["results_wanted"],hours_old=cfg["hours_old"],verbose=1)
        records=json.loads(frame.to_json(orient="records",date_format="iso"))
        for row in records:
            desc=row.get("description") or ""
            job=make_job(row.get("company"),row.get("title"),row.get("job_url_direct") or row.get("job_url"),row.get("location") or "",f"JobSpy · {site}","external",row.get("date_posted"),description=desc,note="发现线索，申请前请核对原始岗位页。")
            if job:jobs.append(job)
        state="error" if errors else "ok" if records else "empty"
        msg=f"{query}：读取 {len(records)} 条，保留 {len(jobs)} 条。"+("；"+" / ".join(errors)[:180] if errors else "")
        return jobs,status(f"jobspy:{site}:{query}",f"JobSpy · {site}","https://github.com/speedyapply/JobSpy",state,msg,jobs)
    except Exception as e:return [],status(f"jobspy:{site}:{query}",f"JobSpy · {site}","https://github.com/speedyapply/JobSpy","error",str(e)[:220],[])
    finally:logger.removeHandler(handler)

def lever(company,url):
    slug=urlparse(url).path.strip("/").split("/")[0]
    if not slug:return []
    body,_,_=fetch(f"https://api.lever.co/v0/postings/{slug}?mode=json",False);jobs=[]
    for row in json.loads(body):
        cat=row.get("categories",{})
        job=make_job(company,row.get("text"),row.get("hostedUrl"),cat.get("location",""),"雇主官网 · Lever","employer",description=row.get("descriptionPlain",""))
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
            if not categorize(row.get("title","")):continue
            detail_url=f"https://{p.netloc}/wday/cxs/{tenant}/{board}"+row["externalPath"]
            detail=requests.get(detail_url,headers={"User-Agent":UA},timeout=20)
            if detail.status_code!=200:continue
            d=detail.json().get("jobPostingInfo",{})
            loc=d.get("location",row.get("locationsText",""))
            if d.get("additionalLocations"):loc+=" "+" ".join(d["additionalLocations"])
            job=make_job(company,d.get("title",row["title"]),f"https://{p.netloc}/{board}"+row["externalPath"],loc,"雇主官网 · Workday","employer",d.get("startDate"),d.get("endDate"),d.get("jobDescription",""))
            if job:jobs.append(job)
        if offset+20>=result.get("total",0):break
    return jobs

def employer(emp):
    jobs=[];errors=[];unchanged=True;pages=0;structured=0
    urls=[emp["url"]]+[w["url"] for w in CONFIG["watch_urls"] if canonical_company(w["company"])==emp["name"]]
    prior=OUTPUT/"snapshot.json"
    if prior.exists():
        # Follow discovered direct employer links on later runs, bounded per employer.
        for j in json.loads(prior.read_text()).get("jobs",[]):
            host=urlparse(j["url"]).netloc
            ownhost=urlparse(emp["url"]).netloc.removeprefix("www.").removeprefix("careers.").removeprefix("jobs.")
            if canonical_company(j["company"])==emp["name"] and (host==ownhost or host.endswith("."+ownhost)):
                urls.append(j["url"])
    seen=set();ats_seen=set()
    for url in list(dict.fromkeys(urls))[:12]:
        if url in seen:continue
        seen.add(url)
        try:
            body,final,same=fetch(url);unchanged=unchanged and same;pages+=1
            found,soup=parse_page(body,final,emp["name"]);jobs.extend(found);structured+=len(found)
            ats_urls=[final]+[urljoin(final,a["href"]) for a in soup.select("a[href]") if re.search(r"jobs\.lever\.co|myworkdayjobs\.com",a["href"])]+re.findall(r'https?://[^\s"<>\x27]+myworkdayjobs[^\s"<>\x27]*',body)
            for ats in ats_urls[:5]:
                host=urlparse(ats).netloc
                if host in ats_seen:continue
                if "jobs.lever.co" in host:ats_seen.add(host);jobs.extend(lever(emp["name"],ats));structured+=1
                elif "myworkdayjobs.com" in host:ats_seen.add(host);jobs.extend(workday(emp["name"],ats));structured+=1
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
                    if not found and re.search(r"/job/|/jobs/[^/?]+|jobdetail|vacancy/",childurl,re.I) and HK.search(txt[:15000]):
                        job=make_job(emp["name"],heading,childurl,"Hong Kong","雇主官网","employer",description=txt[:5000],note="官网未提供结构化日期；请核对入职及毕业资格。")
                        if job and not re.search(r"no longer available|position has been filled|job has expired|job is closed",txt,re.I):jobs.append(job)
                except Exception as e:errors.append(str(e))
        except Exception as e:errors.append(str(e))
    state="partial" if pages else "error"
    msg=f"已检查 {pages} 个页面，找到 {len(jobs)} 条；有限范围检查，未覆盖全部招聘列表。"
    if not pages:msg="；".join(errors)[:220] or "无法获取招聘页"
    elif errors:msg+=" 部分页面未能访问。"
    return jobs,status(emp["id"],emp["name"],emp["url"],state,msg,jobs)

def merge(records):
    result={}
    for j in records:
        if not j:continue
        j["company"]=canonical_company(j["company"])
        j["id"]=sha256((norm(j["company"])+"|"+norm(j["title"])).encode()).hexdigest()[:24]
        old=result.get(j["id"])
        if not old:result[j["id"]]=j;continue
        prefer=j["origin"]=="employer" or (old["source"]=="Workopia" and j["source"]!="Workopia")
        main,extra=(j,old) if prefer else (old,j)
        for field in ("posted","deadline"):
            if not main.get(field):main[field]=extra.get(field)
        result[j["id"]]=main
    return list(result.values())

def retain_history(previous, current, sources, now):
    """Limited searches and source failures never delete earlier discoveries."""
    old = {j["id"]: j for j in previous.get("jobs", [])}
    fresh = merge(current)
    fresh_ids = {j["id"] for j in fresh}
    jobs = merge(list(old.values()) + fresh)
    for job in jobs:
        prior = old.get(job["id"], {})
        job["first_seen"] = prior.get("first_seen") or job.get("first_seen") or now
        job["last_seen"] = now if job["id"] in fresh_ids else prior.get("last_seen") or prior.get("first_seen")
        job.pop("read_at", None)
    by_source = {s["id"]: s for s in previous.get("sources", [])}
    by_source.update({s["id"]: s for s in sources})
    return {"updated_at": now, "employer_count": len(CONFIG["employers"]), "jobs": jobs, "sources": sorted(by_source.values(), key=lambda s: s["id"])}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sources",choices=["all","external","employers"],default="all")
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
        tasks += [(jobspy_query,(site,q)) for site in CONFIG["jobspy"]["sites"] for q in CONFIG["jobspy"]["queries"]]
    if args.sources in ("all","employers"):tasks +=[(employer,(emp,)) for emp in CONFIG["employers"]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map={pool.submit(fn,*a):(fn.__name__,a) for fn,a in tasks}
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
        print("All sources failed; previous public snapshot preserved",file=sys.stderr)
        return 2
    snapshot=retain_history(previous,alljobs,sources,NOW)
    path=Path(args.output)
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(path)
    report={"jobs":len(snapshot["jobs"]),"sources":len(sources),"failed_sources":errors,"file":str(path)}
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0

if __name__=="__main__":sys.exit(main())
