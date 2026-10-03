import unittest
from update import categorize,make_job,iso_date,merge,parse_page,retain_history,main
from unittest.mock import patch
import tempfile
from pathlib import Path
import json
class FilterTests(unittest.TestCase):
 def test_categories(self):
  self.assertEqual(categorize("Supply Chain Intern"),"daily")
  self.assertEqual(categorize("2027 Summer Finance Analyst Internship"),"summer")
  self.assertEqual(categorize("2028 Management Trainee Programme"),"graduate")
 def test_reject_senior_and_non_job(self):
  self.assertIsNone(categorize("Senior Supply Chain Analyst","We hire graduates"))
  self.assertIsNone(categorize("2026 Hasbro Experience Day: Internship Discovery"))
 def test_hk_is_required(self):
  self.assertIsNone(make_job("Example","Supply Chain Intern","https://example.com/job/1","Singapore","test","external"))
 def test_explicit_dates_only(self):
  self.assertIsNone(iso_date("2w"));self.assertIsNone(iso_date("2026-99-99"))
  self.assertEqual(iso_date("Fri Oct 30 23:00:00 UTC 2026"),"2026-10-30")
 def test_prefer_official_and_stable_id(self):
  a=make_job("HSBC","Finance Intern","https://example.com/1","Hong Kong","JobSpy","external",posted="2026-09-30")
  b=make_job("HSBC 汇丰","Finance Intern","https://example.com/2","Hong Kong","Official","employer")
  self.assertEqual(a["id"],b["id"]);out=merge([a,b]);self.assertEqual(len(out),1);self.assertEqual(out[0]["origin"],"employer");self.assertEqual(out[0]["posted"],"2026-09-30")
 def test_microdata(self):
  body='<h1 itemprop="title">Supply Chain Intern</h1><meta itemprop="addressCountry" content="HK"><meta itemprop="datePosted" content="2026-09-22"><meta itemprop="validThrough" content="2026-10-30"><span itemprop="description">Supply planning</span>'
  jobs,_=parse_page(body,"https://example.com/job/1","Example")
  self.assertEqual(jobs[0]["deadline"],"2026-10-30")
 def test_history_retained_without_private_read_state(self):
  old=make_job("Example","Supply Chain Intern","https://example.com/1","Hong Kong","Official","employer")
  old.update(first_seen="2026-09-01T00:00:00Z",read_at="2026-10-01T00:00:00Z")
  out=retain_history({"jobs":[old],"sources":[]},[],[],"2026-10-03T00:00:00Z")
  self.assertEqual(len(out["jobs"]),1)
  self.assertEqual(out["jobs"][0]["first_seen"],"2026-09-01T00:00:00Z")
  self.assertNotIn("read_at",out["jobs"][0])
 def test_rediscovery_preserves_first_seen(self):
  old=make_job("Example","Supply Chain Intern","https://example.com/1","Hong Kong","Official","employer")
  old["first_seen"]="2026-09-01T00:00:00Z"
  fresh={**old,"deadline":"2026-10-30","first_seen":"2026-10-03T00:00:00Z"}
  out=retain_history({"jobs":[old],"sources":[]},[fresh],[],"2026-10-03T00:00:00Z")["jobs"][0]
  self.assertEqual(out["first_seen"],"2026-09-01T00:00:00Z")
  self.assertEqual(out["last_seen"],"2026-10-03T00:00:00Z")
  self.assertEqual(out["deadline"],"2026-10-30")
 def test_all_sources_failure_does_not_overwrite_public_snapshot(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/"jobs.json"
   original=json.dumps({"jobs":[],"sources":[],"updated_at":"old"})
   path.write_text(original)
   config={"jobspy":{"sites":[],"queries":[]},"employers":[]}
   failed=([],{"id":"workopia","name":"Workopia","status":"error","jobs":0})
   with patch("update.CONFIG",config),patch("update.workopia",lambda: failed),patch("update.OUTPUT",Path(directory)),patch("sys.argv",["update.py","--sources","external","--previous",str(path),"--output",str(path)]):
    self.assertEqual(main(),2)
   self.assertEqual(path.read_text(),original)
if __name__=="__main__":unittest.main()
