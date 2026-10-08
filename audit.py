"""Offline release audit. --finalize merges the separately verified official watch run.

Report-only is safe for later maintenance: python audit.py.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import model

ROOT=Path(__file__).resolve().parent
BASELINE='cd89d77ae6bcddb4aa52b410be23c2c0794eb0de'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--finalize',action='store_true');args=parser.parse_args()
    data=json.loads((ROOT/'jobs.json').read_text())
    if args.finalize:
        watch=json.loads((ROOT/'output/watch-snapshot.json').read_text())
        fresh=[j for j in watch['jobs'] if j.get('last_verified')==watch['updated_at']]
        sources=[s for s in watch['sources'] if s['id'].startswith('watch:')]
        health=dict(data['health'])
        data=model.retain(data,fresh,sources,max(data['updated_at'],watch['updated_at']),'manual')
        data['health'].update({k:v for k,v in health.items() if k in ('last_full_success','last_light_success','profile')})
        # Recompute after all collectors so older classifier versions cannot survive migration.
        for j in data['jobs']:
            result=model.classify(j['title'],j.get('description',''),j.get('location',''),j.get('posted'),j.get('deadline'),data['updated_at'],bool(j.get('last_verified')))
            j.update(result)
            if 'May-August' in j['title']:
                j.update(category='holiday',season='summer')
                j['timing']['start']='May-August（原文未注明年份）'
        (ROOT/'jobs.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    samples=json.loads((ROOT/'acceptance-samples.json').read_text())
    lines=['# 发布前数据核验','',f'快照：{data["updated_at"]}。人工对照 {len(samples)} 条官方样本（{len(samples)-2} 条可读官方正文 / 索引，另 2 条实时 ATS 403，明确记录限制）。',
           '', '这些样本用于检查发现与分类，不代表已验证全网召回率。缺失项不计入成功；官网介绍页不强行制造职位。','',
           '| 样本 | 期望 / 实际 | 发现与核验结论 |','|---|---|---|']
    found=correct=0
    for sample in samples:
        key=model.identity({'url':sample['url'],'company':sample['company']})
        rows=[j for j in data['jobs'] if model.identity(j)==key]
        if not rows:
            rows=[j for j in data['jobs'] if model.norm(j['title'])==model.norm(sample['title']) and (model.norm(sample['company']) in model.norm(j['company']) or model.company(sample['company'])==j['company'])]
        states='/'.join(sorted(set(j['state'] for j in rows))) or '未发现'
        expected=sample['expected'];ok=bool(rows) and all((j['state'] in ('active','review','recheck') if expected=='keep' else j['state']==expected) and set(sample['tags'])<=set(j['role_tags']) for j in rows)
        found+=bool(rows);correct+=ok
        conclusion=('通过' if ok else '未通过 / 限制')+'：'+sample['evidence']
        if not rows:conclusion+=' '+sample.get('gap','来源本轮未捕获该链接；需补充发现入口。')
        lines.append(f'| [{sample["company"]} · {sample["title"]}]({sample["url"]}) | {expected} / {states} | {conclusion} |')
    lines+=['',f'样本发现 {found}/{len(samples)}；分类符合预期 {correct}/{len(samples)}（含未发现项，不能当成全网准确率）。','', '## 快照统计','',str(dict(Counter((j['track']+'/'+j['state']) for j in data['jobs']))),'','## 97 家重点雇主入口检查','', '| 公司 | 状态 | 检查说明 |','|---|---|---|']
    statuses={s['id']:s for s in data['sources']}
    for emp in model.CONFIG['employers']:
        s=statuses.get(emp['id'],{})
        lines.append(f'| [{emp["name"]}]({emp["url"]}) | {s.get("status","未检查")} | {s.get("message","").replace("|","/")} |')
    try:
        baseline=json.loads(subprocess.check_output(['git','show',BASELINE+':jobs.json'],cwd=ROOT,text=True))
        old_ids={j['id'] for j in baseline['jobs']};represented={j['id'] for j in data['jobs']}|{a for j in data['jobs'] for a in j.get('legacy_ids',[])}
        lines+=['','## 旧记录迁移','',f'旧快照 {len(old_ids)} 个 ID；当前直接或别名保留 {len(old_ids & represented)} 个；未保留 {len(old_ids-represented)} 个。',
                '','| 原岗位 | 新分类 / 状态 | 原因 |','|---|---|---|']
        for old in baseline['jobs']:
            row=next((j for j in data['jobs'] if j['id']==old['id'] or old['id'] in j.get('legacy_ids',[])),None)
            if row and (row['category']!=old['category'] or row['state']!='active'):
                lines.append(f'| {old["company"]} · {old["title"]} | {row["category"]} / {row["state"]} | {"；".join(row["review_reasons"])} |')
    except subprocess.CalledProcessError:lines+=['','本地无旧 commit，略过旧 ID 审计。']
    (ROOT/'AUDIT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'samples':len(samples),'found':found,'matched':correct,'jobs':len(data['jobs']),'report':'AUDIT.md'}))

if __name__=='__main__':main()
