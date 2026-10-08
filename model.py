"""Evidence-bounded classification and lossless public history. No network calls."""
import hashlib
import json
import re
import unicodedata
import html
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
RULES = json.loads((ROOT / 'rules.json').read_text())
CONFIG = json.loads((ROOT / 'config.json').read_text())
WATCH = json.loads((ROOT / 'official-watch.json').read_text())
HK = re.compile(r'hong\s*kong|香港|\bHK\b', re.I)

def text(value):
    value = BeautifulSoup(html.unescape(str(value or '')), 'html.parser').get_text(' ', strip=True)
    value = re.sub(r'\\([&*_-])', r'\1', value)
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value).replace('–', '-').replace('—', '-').replace('‑', '-')).strip()

def norm(value):
    return re.sub(r'[^\w]', '', unicodedata.normalize('NFKC', value).casefold())

def company(value, url=''):
    value = RULES.get('company_overrides', {}).get(canonical_url(url), value)
    value = text(value)
    n = norm(value)
    matches = []
    for emp in CONFIG['employers']:
        aliases = [emp['name'], re.split(r'[\u4e00-\u9fff]', emp['name'])[0].strip()] + emp['aliases']
        for alias in aliases:
            if alias and (n == norm(alias) or (len(norm(alias)) >= 5 and n.startswith(norm(alias)))):
                matches.append((len(norm(alias)), emp['name']))
    return max(matches)[1] if matches else value

def canonical_url(url):
    p = urlsplit(str(url or ''))
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('trk', 'trackingid', 'refid', 'source', 'gh_src', 'feedid', 'iis', 'indeed-apply-token')]
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix('www.'), p.path.rstrip('/'), urlencode(sorted(query)), ''))

def identity(job):
    url = canonical_url(job['url'])
    for seed in WATCH:
        if url in [canonical_url(u) for u in seed.get('same_job_urls',[])]:url=canonical_url(seed['url']);break
    p = urlsplit(url)
    gh = dict(parse_qsl(p.query)).get('gh_jid')
    if 'janestreet.com' in p.netloc:
        m=re.search(r'/(?:apply|position)/(\d+)$',p.path)
        if m:return 'greenhouse:'+m[1]
    if gh: return 'greenhouse:' + gh
    if 'greenhouse.io' in p.netloc:
        m = re.search(r'/(\d+)$', p.path)
        if m: return 'greenhouse:' + m[1]
    if 'lvmh.com' in p.netloc:
        m = re.search(r'/([A-Z]{2,}\d+)$', p.path)
        if m: return 'lvmh:' + m[1]
    if 'myworkdayjobs.com' in p.netloc or 'myworkdaysite.com' in p.netloc:
        m=re.search(r'_([A-Z]+[0-9]+(?:-\d+)?)',p.path)
        tenant=p.netloc.split('.')[0] if 'myworkdayjobs.com' in p.netloc else p.path.split('/')[2]
        if m:return 'workday:'+tenant+':'+m[1]
    if job.get('ats_id'):
        return norm(job['company']) + ':' + str(job['ats_id'])
    return url

def hit(key, value):
    return bool(re.search(RULES[key], value, re.I))

def role_text(description):
    """Do not allow company introductions, benefits or equal-opportunity text to tag jobs."""
    description = text(description)
    start = re.search(r'(?:your responsibilities|key responsibilities|job responsibilities|responsibilities\s*:|what you.ll (?:be )?do(?:ing)?|what you will (?:be )?do(?:ing)?|about the (?:role|position)|job description|工作职责|工作職責)', description, re.I)
    if start: description = description[start.start():]
    description = re.split(r'about (?:us|the company)|company overview|who we are|equal opportunity|our benefits|what we offer you|offers you may be interested|关于我们|關於我們', description, flags=re.I)[0]
    return description[:12000]

def snippets(description, pattern, limit=4):
    parts = re.split(r'(?<=[.!?。；;])\s+|\n', text(description))
    found = [p.strip()[:420] for p in parts if re.search(pattern, p, re.I)]
    return list(dict.fromkeys(found))[:limit]

def classify(title, description='', location='', posted=None, deadline=None, now=None, official=False):
    now = now or datetime.now(timezone.utc).isoformat()
    today = now[:10]
    title, description, location = text(title), text(description), text(location)
    duties = role_text(description)
    evidence = title + ' ' + duties
    reasons, excluded = [], []
    # Explicit job location in description overrides a third-party country tag.
    loc_match = re.search(r'(?:job location|work location|based in|location\s*:|工作地点|工作地點)\s*([^.;\n]{2,110})', description, re.I)
    actual = loc_match[1] if loc_match else location
    actual = re.split(r'Candidates|Programme|Program|Department|Who qualifies|工作职责|工作職責',actual,flags=re.I)[0].strip()
    if not HK.search(actual):
        if actual and not re.search(r'remote|multiple|various|asia|apac|global', actual, re.I): excluded.append('实际工作地点不在香港')
        else: reasons.append('工作地点未明确包含香港')
    internship = hit('intern', title) or bool(re.search(r'(?:as an? intern|this internship|internship (?:programme|program|position)|student placement|实习生|實習生)', duties, re.I))
    graduate = hit('graduate', title) or bool(re.search(r'(?:this role is part of (?:the|our)|as a) (?:graduate trainee|management trainee)', duties, re.I))
    if re.search(r'\b(?:manager|specialist|officer|associate)\b', title, re.I) and not (hit('intern',title) or hit('graduate',title)):
        internship = bool(re.search(r'\bas an? intern\b|this (?:is an?|role is an?) internship', duties, re.I))
    if not (internship or graduate): excluded.append('不是明确的实习、学生 Placement 或正式毕业生项目')
    if hit('non_job', title): excluded.append('招聘活动或人才库，不是具体岗位')
    if hit('irrelevant', title): excluded.append('非目标商科或供应链岗位')
    if hit('senior', title) and not graduate: excluded.append('明确资深岗位')
    # A career paragraph mentioning internships does not make an experienced vacancy a student role.
    if not hit('intern', title) and not hit('graduate', title) and re.search(r'(?:at least|minimum(?: of)?|over|more than)\s+(?:[3-9]|\d{2})\s*(?:years|年)', duties, re.I):
        excluded.append('要求多年专业工作经验')
    tag_duties = re.split(r'skills\s*&\s*requirements|qualifications|required main study|requirements\s*:|who qualifies|what you (?:will )?bring|about (?:the company|us)|our mission', duties, flags=re.I)[0]
    # Generic terms have non-supply-chain meanings: expert/data sourcing, insurance distribution,
    # event logistics, research degrees, and IT asset inventory are not SC job functions.
    non_sc = re.compile(RULES['non_sc_context'], re.I)
    tag_duties = '. '.join(part for part in re.split(r'[.!?]', tag_duties) if not non_sc.search(part))
    tag_evidence = title + ' ' + tag_duties
    tags = [key for key, rule in RULES['directions'].items() if re.search(rule['pattern'], tag_evidence, re.I)]
    if 'logistics' in tags and re.search(r'distribution',tag_evidence,re.I) and not re.search(r'\b(?:logistics|freight|shipping|warehous[a-z]*|transportation|fulfil[l]?ment|supply chain|physical distribution)\b|库存|物流',tag_evidence,re.I): tags.remove('logistics')
    if hit('non_sc_titles',title) and not re.search(r'procurement|supply chain|logistics|inventory|(?:demand|supply|material) planning',title,re.I):
        # Incidental administrative tasks do not change the primary function.
        tags = []
    sc_context = bool(tags)
    if sc_context and re.search(r'operational excellence|operations analytics', evidence, re.I) and 'analytics' not in tags: tags.append('analytics')
    if re.search(r'supply chain (?:financ|management).*transaction|transaction banking|trade financ|supply chain financ', evidence, re.I):
        tags = [t for t in tags if t != 'analytics']
        if not re.search(r'(?:raise|create|manage) purchase orders|vendor contracts|supplier selection', duties, re.I): tags = []
    if not tags and not hit('business', evidence):
        if re.search(r'internship (?:program|programme)|management trainee|graduate (?:program|programme)|^(?:winter|summer) internship\b', title, re.I): reasons.append('通用项目，具体职能待核对')
        else: excluded.append('缺少目标职能证据')
    # Season must refer to this role, not a possible return offer or unrelated programme.
    season_text = title
    if not (hit('winter', title) or hit('summer', title)):
        season_text += ' ' + ' '.join(snippets(description, r'(?:winter|summer|寒假|暑假|暑期|寒期).{0,25}(?:intern|placement|实习|實習)|(?:internship|programme).{0,25}(?:winter|summer)', 2))
    winter, summer = hit('winter', season_text), hit('summer', season_text)
    season = 'both' if winter and summer else 'winter' if winter else 'summer' if summer else 'none'
    category = 'holiday' if internship and season != 'none' else 'daily' if internship else 'holiday' if re.search(r'\b(?:summer|winter) analyst\b', title, re.I) else 'graduate'
    if category == 'holiday' and season == 'none': season = 'summer' if hit('summer', title) else 'winter'
    years = sorted(set(re.findall(r'\b20[2-3]\d\b', title)))
    current_year = int(today[:4])
    crossing_winter = winter and bool(re.search(r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?)\s+'+str(current_year),description,re.I))
    if years and max(map(int, years)) < current_year and not crossing_winter: excluded.append('标题项目年份已过期')
    elif years and category == 'holiday' and season == 'summer' and max(map(int, years)) < RULES['target_summer_year']:
        excluded.append('暑期项目不在目标申请周期')
    elif years and category == 'graduate' and max(map(int, years)) < current_year + 1: excluded.append('毕业项目年份已过期')
    if category == 'graduate' and ('2027' in years or not years): reasons.append('2027 年 11 月毕业；需核对毕业窗口及正式入职日期')
    if re.search(r'graduat(?:e|ing|ion).{0,60}between\s+(?:December|Dec)\s+2027',description,re.I): reasons.append('毕业窗口从 2027 年 12 月起，与预计 11 月毕业有冲突，须确认资格')
    if re.search(r'graduat(?:e|ing).{0,25}(?:by|before)\s+(?:January|February|March|April|May|June|July|August|September|October)\s+2027',description,re.I): reasons.append('要求在 2027 年 11 月之前毕业，与预计毕业时间冲突')
    if re.search(r'potential.{0,30}(?:openings|functions)|one of (?:the following|our) (?:departments|business units)',description,re.I): reasons.append('多职能项目，供应链名额和实际分配待确认')
    if re.search(r'January|Jan\b|一月',title,re.I) and re.search(r'Start date\s*:\s*01\.06\.',description,re.I): reasons.append('标题 / 正文与页面入职字段冲突，请核实实际开始日期')
    if re.search(r'undergraduate students|undergraduates',description,re.I) and not re.search(r'master|postgraduate|or above',description,re.I): reasons.append('说明主要面向本科生，研究生资格待确认')
    timing = {
        'start': ' / '.join(snippets(description, r'(?:start date|commenc|starting|starts? in|join.{0,15}(?:January|February|March|April|May|June|July|August|September|October|November|December)|入职|入職|开始日期)', 2)),
        'duration': ' / '.join(snippets(description, r'\b\d+[ -]*(?:week|month)s?\b|[0-9一二三四五六七八九十]+\s*个?月|时长|時長', 2)),
        'days': ' / '.join(snippets(description, r'(?:[1-7]|one|two|three|four|five)\s*(?:full[ -]?)?days?.{0,18}(?:week|weekly)|每周|每週', 2)),
    }
    requirements = list(dict.fromkeys(snippets(description,r'graduat.{0,60}(?:20\d{2}|between|by)|penultimate|visa|right to work',4)+snippets(description, r'eligible|eligibility|student|bachelor|master|degree|cantonese|mandarin|work permit|毕业|畢業|粤语|粵語', 4)))[:6]
    if not deadline and not timing['start'] and not years: reasons.append('申请窗口 / 入职时间未知')
    # The short list shows actual evidence fragments, not whole paragraphs starting with navigation.
    starts=re.findall(r'(?:start date(?: and duration)?|program(?:me)? commences|commencing in|commencement period|internship period)\s*[:|]?\s*(.{3,100})',description,re.I)
    starts=[re.split(r'\s+(?:Location:|Candidates|Application|Crafting|Reference:|Job responsibilities)',s,flags=re.I)[0].strip() for s in starts]
    starts=[re.split(r'\s+(?:You Should|Requirements|Qualifications)',s,flags=re.I)[0] for s in starts if re.search(r'20\d{2}|ASAP|immediate',s,re.I)]
    if starts:timing['start']=' / '.join(dict.fromkeys(starts[:3]))
    durations=re.findall(r'\b(?:\d+(?:\s*(?:to|-|or)\s*\d+)?|one|two|three|four|five|six|twelve)[ -]*(?:week|month)s?\b',description,re.I)
    if durations:timing['duration']=' / '.join(dict.fromkeys(durations[:4]))
    if not description: reasons.append('尚未取得完整岗位说明')
    state = 'excluded' if excluded else 'review' if reasons else 'active'
    if deadline and deadline < today: state = 'archived'; reasons.append('明确截止日期已过')
    if official and hit('closed',description):
        state = 'archived'; reasons.append('官方页面明确关闭')
    return {'category': category, 'season': season, 'role_tags': tags, 'track': 'supply' if tags else 'business',
            'state': state, 'review_reasons': list(dict.fromkeys(excluded + reasons)), 'timing': timing,
            'requirements': requirements, 'project_years': years, 'location': actual,
            'match_evidence': [title] + snippets(tag_duties, '|'.join(RULES['directions'][t]['pattern'] for t in tags), 2) if tags else [title]}

def make(company_name, title, url, location, source, origin, posted=None, deadline=None, description='', note='', now=None, **_):
    if not company_name or not title or not str(url).startswith(('https://', 'http://')): return None
    now = now or datetime.now(timezone.utc).isoformat()
    record = {'company': company(company_name, url), 'title': text(title), 'url': canonical_url(url), 'source': source,
              'origin': origin, 'posted': posted, 'deadline': deadline, 'note': note, 'description': text(description),
              'first_seen': now, 'last_seen': now, 'last_verified': now if origin == 'employer' else None}
    record.update(classify(title, description, location, posted, deadline, now, origin == 'employer'))
    record['id'] = hashlib.sha256(identity(record).encode()).hexdigest()[:24]
    record['watchlist'] = any(e['name'] == record['company'] for e in CONFIG['employers'])
    record['sources'] = [{'name': source, 'url': record['url'], 'seen_at': now, 'official': origin == 'employer'}]
    record['legacy_ids'] = []
    return record

def merge(records):
    result = {}
    for record in records:
        if not record: continue
        j = dict(record)
        key = identity(j)
        old = result.get(key)
        if old:
            # Official description wins; do not prefer a blank official listing over full evidence.
            score = lambda x: (x['origin'] == 'employer', bool(x.get('description')), x.get('last_seen') or '')
            main, extra = (j, old) if score(j) >= score(old) else (old, j)
            j = dict(main)
            for field in ('deadline', 'posted', 'description', 'last_verified'):
                if not j.get(field): j[field] = extra.get(field)
            sources = {(s['name'], s['url']): s for s in extra.get('sources', []) + main.get('sources', [])}
            j['sources'] = list(sources.values())
            j['legacy_ids'] = sorted(set(extra.get('legacy_ids', []) + main.get('legacy_ids', []) + [old['id'], record['id']]) - {j['id']})
            j['first_seen'] = min(x for x in (old.get('first_seen'), record.get('first_seen')) if x)
        result[key] = j
    return list(result.values())

SIGNIFICANT = ('deadline', 'url', 'timing', 'requirements', 'category', 'season', 'location')

def retain(previous, current, sources, now, profile='full'):
    migrated = []
    for old in previous.get('jobs', []):
        j = make(old['company'], old['title'], old['url'], old.get('location', ''), old['source'], old['origin'],
                 old.get('posted'), old.get('deadline'), old.get('description', ''), old.get('note', ''), now=now)
        if not j: continue
        j.update({k: v for k, v in old.items() if k not in ('read_at',)})
        j['company'] = company(j['company'], j['url'])
        j.update(classify(old['title'], old.get('description', ''), old.get('location', ''), old.get('posted'), old.get('deadline'), now, bool(old.get('last_verified'))))
        if previous.get('version', 1) < 2:
            j['last_verified'] = None
        j['last_seen'] = old.get('last_seen') or old.get('first_seen')
        j['sources'] = old.get('sources') or [{'name': old['source'], 'url': old['url'], 'seen_at': j['last_seen'], 'official': old['origin'] == 'employer'}]
        migrated.append(j)
    old_by_key = {identity(j): j for j in merge(migrated)}
    fresh = merge(current)
    new_count = changed_count = 0
    for j in fresh:
        key = identity(j)
        prior = old_by_key.get(key)
        if prior:
            # A daily aggregator refresh must not replace an official page/description
            # verified by the full run. Keep the new discovery in the source trail.
            if prior['origin'] == 'employer' and j['origin'] != 'employer':
                found_at = j['last_seen']
                j = merge([j, prior])[0]
                j['last_seen'] = max(found_at, prior.get('last_seen') or '')
            j['id'] = prior['id']
            j['legacy_ids'] = sorted(set(j.get('legacy_ids', []) + prior.get('legacy_ids', [])) - {j['id']})
            j['first_seen'] = prior['first_seen']
            j['changed_at'] = prior.get('changed_at')
            # A less informative source cannot erase previously verified detail.
            if not j.get('description') and prior.get('description'):
                for field in ('description', 'timing', 'requirements', 'role_tags', 'category', 'season', 'track', 'match_evidence'):
                    j[field] = prior.get(field, j.get(field))
            if not j.get('deadline'): j['deadline'] = prior.get('deadline')
            if not j.get('last_verified'): j['last_verified'] = prior.get('last_verified')
            j['sources'] = list({(s['name'], s['url']): s for s in prior.get('sources', []) + j.get('sources', [])}.values())
            if previous.get('version') == 2 and any(prior.get(k) != j.get(k) for k in SIGNIFICANT):
                j['changed_at'] = now; changed_count += 1
        else:
            new_count += j['state'] not in ('excluded', 'archived')
        old_by_key[key] = j
    jobs = list(old_by_key.values())
    for j in jobs:
        if j.get('deadline') and j['deadline'] < now[:10]: j['state'] = 'archived'
        confirmed = j.get('last_verified') or j.get('first_seen')
        if j['state'] not in ('excluded', 'archived') and confirmed and (datetime.fromisoformat(now.replace('Z', '+00:00')) - datetime.fromisoformat(confirmed.replace('Z', '+00:00'))).days >= RULES['stale_days']:
            j['state'] = 'recheck'
            j['review_reasons'] = list(dict.fromkeys(j.get('review_reasons', []) + ['连续 30 天未获官方重新确认，待复查']))
        j.pop('read_at', None)
    by_source = {s['id']: s for s in previous.get('sources', [])}
    by_source.update({s['id']: s for s in sources})
    health = dict(previous.get('health', {}))
    success = any(s['status'] in ('ok', 'unchanged', 'empty', 'partial') for s in sources)
    if success and profile in ('light','full'): health['last_' + profile + '_success'] = now
    if success and profile == 'full': health['last_light_success'] = now
    health.update(last_attempt=now, profile=profile, failed_sources=sum(s['status'] == 'error' for s in sources), new_count=new_count, changed_count=changed_count)
    return {'version': 2, 'updated_at': now if success else previous.get('updated_at'), 'employer_count': len(CONFIG['employers']), 'health': health,
            'jobs': sorted(jobs, key=lambda j: j['id']), 'sources': sorted(by_source.values(), key=lambda s: s['id'])}
