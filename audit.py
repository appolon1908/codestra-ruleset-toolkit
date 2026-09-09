import base64, json, subprocess, sys, yaml

OWNER = "appolon1908-hue"

def gh(*a):
    p = subprocess.run(["gh", *a], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])
    return p.stdout

def audit(repo):
    print(f"\n{'='*70}\n{repo}\n{'='*70}")
    wfs = json.loads(gh("api", f"repos/{OWNER}/{repo}/actions/workflows", "--paginate"))["workflows"]
    for wf in sorted(wfs, key=lambda w: w["path"]):
        path = wf["path"]
        if not path.startswith(".github/workflows"):
            continue
        try:
            raw = base64.b64decode(json.loads(gh("api", f"repos/{OWNER}/{repo}/contents/{path}"))["content"])
            doc = yaml.safe_load(raw)
        except Exception as e:
            print(f"  ?? {path}  (parse: {e})".replace("\n", " ")[:150])
            continue
        if not isinstance(doc, dict):
            continue
        on = doc.get("on", doc.get(True))          # YAML parses bare `on:` as True
        pr_ok, note = False, ""
        if isinstance(on, dict) and "pull_request" in on:
            cfg = on["pull_request"] or {}
            pr_ok = True
            if isinstance(cfg, dict):
                if "paths" in cfg or "paths-ignore" in cfg:
                    note += " PATH-FILTERED"
                if "branches" in cfg:
                    note += f" branches={cfg['branches']}"
                if "types" in cfg:
                    note += f" types={cfg['types']}"
        elif isinstance(on, list) and "pull_request" in on:
            pr_ok = True
        jobs = doc.get("jobs") or {}
        names = [ (j.get("name") if isinstance(j, dict) and j.get("name") else jid)
                  for jid, j in jobs.items() ]
        flag = "PR " if pr_ok else "-- "
        print(f"  {flag}{path}{note}")
        if pr_ok and names:
            for n in names:
                print(f"        check: {n}")

for repo in sys.argv[1:]:
    audit(repo)
