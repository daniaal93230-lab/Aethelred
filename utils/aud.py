import pathlib, time, json

LOG = pathlib.Path("risk_audit_log.md")


def append_audit(reason: str, details: dict):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    line = f"| {ts} | {reason} | `{json.dumps(details, separators=(',', ':'))}` |\n"
    if not LOG.exists():
        LOG.write_text("| ts | reason | details |\n|---|---|---|\n")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
