import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import model
import update

NOW='2026-10-08T00:00:00+00:00'
def classify(title,description='',location='Hong Kong',**kw):
    return model.classify(title,description,location,now=NOW,**kw)
def job(title='Supply Chain Intern',url='https://example.com/jobs/1',**kw):
    return model.make('Example',title,url,'Hong Kong','Official','employer',now=NOW,**kw)

class Filters(unittest.TestCase):
    def test_synonyms(self):
        for title,tag in [('Procurement Intern','procurement'),('Purchasing Intern','procurement'),('Buyer Intern','procurement'),('採購實習生','procurement'),('Demand Planning Intern','planning'),('Material Planning Intern','planning'),('Inventory Intern','planning'),('補貨實習生','planning'),('Logistics Intern','logistics'),('Freight Intern','logistics'),('Fulfillment Intern','logistics'),('倉儲實習生','logistics'),('Product Supply Intern','analytics')]:
            with self.subTest(title=title): self.assertIn(tag,classify(title)['role_tags'])
    def test_resources_not_sourcing(self):
        self.assertFalse(classify('Human Resources Intern')['role_tags'])
        self.assertEqual(classify('Human Resources Intern')['state'],'excluded')
    def test_locations(self):
        self.assertEqual(classify('Procurement Intern','Location: London. Our Hong Kong office is growing.','Hong Kong')['state'],'excluded')
        self.assertNotEqual(classify('Procurement Intern',location='London; Hong Kong')['state'],'excluded')
        self.assertEqual(classify('Procurement Intern',location='')['state'],'review')
    def test_no_ordinary_jobs(self):
        self.assertEqual(classify('Supply Chain Coordinator (Fresh Graduate Welcome)')['state'],'excluded')
        self.assertEqual(classify('Procurement Specialist','Minimum 5 years experience. We offer internships elsewhere.')['state'],'excluded')
    def test_graduate_manager(self):
        r=classify('2027 P&G Graduate Program - Product Supply Manager')
        self.assertEqual(r['category'],'graduate');self.assertNotEqual(r['state'],'excluded')
        self.assertTrue(any('毕业' in s for s in r['review_reasons']))
    def test_seasons(self):
        self.assertEqual(classify('Winter Internship 2026','Commences December 2026 through January 2027.')['season'],'winter')
        self.assertEqual(classify('Data Analytics Internship Winter or Summer2027')['season'],'both')
        self.assertEqual(classify('Supply Chain Intern','Starting January 2027.')['category'],'daily')
    def test_stale_daily(self):
        self.assertEqual(classify('Aon Internship Programme 2024')['state'],'excluded')
    def test_crossing_winter_next_year(self):
        self.assertNotEqual(model.classify('Winter Internship 2026','Internship December 2026 - January 2027.','Hong Kong',now='2027-01-02T00:00:00Z')['state'],'excluded')
    def test_graduation_conflict(self):
        self.assertEqual(classify('2027 Summer Analyst','Students graduating between December 2027 and June 2028.')['state'],'review')
        self.assertEqual(classify('Sales Intern','Be expected to graduate by July 2027. Starting March 2027.')['state'],'review')
    def test_lvmh_nav_location(self):
        body='<nav>Paris</nav><h1>Supply Chain Intern</h1><p>Place of employment : Hong Kong SAR, Hong Kong SAR Contrat type : Internship</p><p>Starting November 2026.</p>'
        rows,_=update.parse_page(body,'https://www.lvmh.com/en/join-us/our-job-offers/MHAP01267','LVMH')
        self.assertIn('Hong Kong',rows[0]['location']);self.assertNotEqual(rows[0]['state'],'excluded')
    def test_semantics(self):
        for title,desc in [('Distribution Strategy Internship 2027','Insurance sales channels.'),('Financial Planning Intern','Planning for customers.'),('Quantitative Analytics Intern','Degree in Operations Research.'),('Data Engineering Intern','Expert sourcing. Data sourcing projects.'),('Financial Analyst Intern','Our mission is to turn inventory into opportunity.')]:
            with self.subTest(title=title): self.assertFalse(classify(title,desc)['role_tags'])
        self.assertEqual(classify('2027 Graduate Programme - Transaction Banking, Supply Chain Management')['track'],'business')
    def test_closed(self):
        self.assertEqual(classify('Logistics Intern','Application period: Closed',official=True)['state'],'archived')
        self.assertNotEqual(classify('Logistics Intern','Application deadline: 16 October 2026',official=True)['state'],'archived')
    def test_date_parser(self):
        self.assertIsNone(update.iso_date('2w'));self.assertIsNone(update.iso_date('2026-99-99'))
        self.assertEqual(update.iso_date('Fri Oct 30 23:00:00 UTC 2026'),'2026-10-30')
    def test_microdata(self):
        body='<h1 itemprop="title">Supply Chain Intern</h1><meta itemprop="addressCountry" content="HK"><meta itemprop="validThrough" content="2026-10-30"><span itemprop="description">Supply planning</span>'
        rows,_=update.parse_page(body,'https://example.com/job/1','Example')
        self.assertEqual(rows[0]['deadline'],'2026-10-30')
    def test_company(self):
        self.assertEqual(model.company('Moët Hennessy'),'LVMH')
        self.assertIn('OOCL',model.company('OOCL'))
        self.assertIn('Coca-Cola',model.company('Swire Coca-Cola'))
    def test_real_false_positives(self):
        for title,desc in [('Distribution Intern','We are fulfilling our potential. What You’ll Be DOING: support insurance sales.'),('Associate Intern','Arrange expert\\-related logistics.'),('AI Observability Engineer Intern','Shipping web services.'),('Transaction Services Intern','Supply chain financing and trade finance.')]:
            with self.subTest(title=title):self.assertFalse(classify(title,desc)['role_tags'])
        self.assertEqual(classify('Sales - Greater Asia','Minimum of 3 years working experience. Our internship programme is also available.')['state'],'excluded')

class Adapters(unittest.TestCase):
    def test_greenhouse(self):
        raw={'jobs':[{'title':'Procurement Intern','absolute_url':'https://boards.greenhouse.io/a/jobs/123','location':{'name':'Hong Kong'},'content':'Purchasing and vendor management.'}]}
        with patch('update.fetch',return_value=(json.dumps(raw),'',False)):
            rows=update.greenhouse('A','https://boards.greenhouse.io/a')
        self.assertEqual(rows[0]['role_tags'],['procurement'])
    def test_smartrecruiters(self):
        index={'totalFound':1,'content':[{'id':'123','location':{'city':'Hong Kong'}}]}
        detail={'name':'Supply Planning Intern','jobAd':{'sections':{'jobDescription':{'text':'Inventory replenishment.'}}}}
        with patch('update.fetch',side_effect=[(json.dumps(index),'',False),(json.dumps(detail),'',False)]):
            rows=update.smartrecruiters('A','https://jobs.smartrecruiters.com/A')
        self.assertEqual(rows[0]['role_tags'],['planning'])

class History(unittest.TestCase):
    def test_official_survives_light_refresh(self):
        old=job(description='Supply planning.',deadline='2026-11-01')
        fresh={**job(description='Inventory.'),'origin':'external','source':'FreeHire'}
        fresh['sources']=[{'name':'FreeHire','url':fresh['url'],'seen_at':NOW,'official':False}]
        result=model.retain({'version':2,'jobs':[old]},[fresh],[],NOW)['jobs'][0]
        self.assertEqual(result['origin'],'employer');self.assertEqual(result['description'],old['description'])
        self.assertEqual(len(result['sources']),2)
    def test_no_title_only_merge(self):
        self.assertEqual(len(model.merge([job(),job(url='https://example.com/jobs/2')])),2)
    def test_merge_url_and_prefer_official(self):
        a=job();b={**job(url='https://example.com/jobs/1?utm_source=x'),'origin':'external','source':'FreeHire'}
        rows=model.merge([a,b]);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['origin'],'employer')
    def test_greenhouse_identity(self):
        a=job(url='https://job-boards.greenhouse.io/firm/jobs/8693354002')
        b=job(url='https://www.janestreet.com/apply/8693354002?gh_jid=8693354002')
        self.assertEqual(model.identity(a),model.identity(b))
    def test_preservation_and_changes(self):
        old=job();old.update(id='a'*24,first_seen='2026-09-01T00:00:00Z',read_at=NOW)
        prev={'version':2,'jobs':[old],'sources':[]}
        fresh=job(deadline='2026-10-30')
        result=model.retain(prev,[fresh],[],NOW)['jobs'][0]
        self.assertEqual(result['id'],old['id']);self.assertEqual(result['first_seen'],old['first_seen'])
        self.assertEqual(result['changed_at'],NOW);self.assertNotIn('read_at',result)
    def test_repeat_not_new(self):
        j=job();prev={'version':2,'jobs':[j],'sources':[]}
        result=model.retain(prev,[{**j,'posted':'2026-10-08'}],[],NOW)
        self.assertEqual(result['health']['new_count'],0);self.assertEqual(result['health']['changed_count'],0)
    def test_failed_source_retains_history(self):
        old=job();old['last_verified']='2026-08-01T00:00:00Z'
        result=model.retain({'version':2,'jobs':[old]},[],[{'id':'a','status':'error'}],NOW)
        self.assertEqual(len(result['jobs']),1);self.assertEqual(result['jobs'][0]['state'],'recheck')
    def test_all_fail_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'jobs.json';original='{"jobs":[],"sources":[],"updated_at":"old"}';path.write_text(original)
            failed=([],{'id':'x','name':'x','status':'error','jobs':0})
            with patch('update.workopia',return_value=failed),patch('update.freehire',return_value=failed),patch('update.OUTPUT',Path(d)),patch('sys.argv',['update.py','--profile','light','--previous',str(path),'--output',str(path)]):self.assertEqual(update.main(),2)
            self.assertEqual(path.read_text(),original)
    def test_cap_reported(self):
        cfg={**model.RULES,'freehire':{'base_url':'https://example.com','page_size':1,'max_pages':1,'queries':[{'q':'intern'}]}}
        raw=json.dumps({'jobs':[{'company':'A','title':'Procurement Intern','location':'Hong Kong','url':'https://example.com/1'}],'total':2})
        with patch('model.RULES',cfg),patch('update.fetch',return_value=(raw,'',False)):
            _,s=update.freehire();self.assertEqual(s['status'],'partial')
    def test_ignored_parameter_not_success(self):
        cfg={**model.RULES,'freehire':{'base_url':'https://example.com','page_size':1,'max_pages':1,'queries':[{'q':'intern'}]}}
        with patch('model.RULES',cfg),patch('update.fetch',return_value=('{"ignored_params":["countries"],"jobs":[]}','',False)):
            _,s=update.freehire();self.assertEqual(s['status'],'error')

if __name__=='__main__':unittest.main()
