import base64, json, subprocess, sys, yaml
OWNER="appolon1908-hue"
def gh(*a):
    p=subprocess.run(["gh",*a],capture_output=True,text=True)
    if p.returncode: raise RuntimeError(p.stderr.strip()[:200])
    return p.stdout
repo, path = sys.argv[1], sys.argv[2]
raw=base64.b64decode(json.loads(gh("api",f"repos/{OWNER}/{repo}/contents/{path}"))["content"])
doc=yaml.safe_load(raw)
on=doc.get("on",doc.get(True))
print(f"{repo} :: {path}")
print(f"  on: {json.dumps(on)}")
for jid,j in (doc.get("jobs") or {}).items():
    nm=j.get("name") or jid
    cond=j.get("if")
    needs=j.get("needs")
    print(f"  - {nm!r:<50} if={cond!r} needs={needs}")
