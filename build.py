"""Build a portable static folder from explicitly public files only."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOB_KEYS = {"id","company","title","category","origin","posted","deadline","url","source","note","location","first_seen","last_seen","state"}
SOURCE_KEYS = {"id","name","url","status","message","jobs","checked_at"}

def validate(data):
    assert set(data) == {"updated_at","employer_count","jobs","sources"}, "Unexpected public snapshot fields"
    assert data["jobs"] and len(data["jobs"]) <= 20000
    assert len({j["id"] for j in data["jobs"]}) == len(data["jobs"]), "Duplicate job IDs"
    for job in data["jobs"]:
        assert set(job) <= JOB_KEYS, "Private or unknown field in public jobs"
        assert job["category"] in ("daily","summer","graduate")
        assert job["origin"] in ("employer","external")
        assert job["url"].startswith(("https://","http://"))
        assert len(job["id"]) == 24 and all(c in "abcdef0123456789" for c in job["id"])
    for source in data["sources"]:
        assert set(source) <= SOURCE_KEYS, "Unexpected source fields"
    return data

def main():
    data = validate(json.loads((ROOT/"jobs.json").read_text()))
    out = ROOT/"dist"
    out.mkdir(exist_ok=True)
    files = ("index.html","style.css","core.js","app.js","jobs.json")
    # Never package the repository root, raw backups, local caches, or credentials.
    if set(p.name for p in out.iterdir()) - set(files) - {"jobs-data.js", ".nojekyll"}:
        raise RuntimeError("Unexpected files in dist; refusing to publish an unaudited directory")
    for name in files:
        shutil.copyfile(ROOT/name, out/name)
    encoded = json.dumps(data,ensure_ascii=False,separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    (out/"jobs-data.js").write_text("window.JOB_DATA="+encoded+";\n",encoding="utf-8")
    (out/".nojekyll").touch()
    print(json.dumps({"jobs":len(data["jobs"]),"files":len(list(out.iterdir())),"output":str(out)}))

if __name__ == "__main__":
    main()
