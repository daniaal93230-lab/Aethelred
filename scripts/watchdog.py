import time
import argparse
import urllib.request
import urllib.error
import json


def get(url: str, timeout: float = 3.0):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read()


def post(url: str, timeout: float = 5.0):
    data = json.dumps({}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read()


def main():
    ap = argparse.ArgumentParser(description="Aethelred watchdog")
    ap.add_argument("--base", default="http://127.0.0.1:8080", help="API base URL")
    ap.add_argument("--interval", type=int, default=3, help="seconds between probes")
    ap.add_argument("--failures", type=int, default=3, help="consecutive failures to trigger flatten")
    args = ap.parse_args()

    fail = 0
    # allow apps that mount ops routes without prefix
    health = f"{args.base.rstrip('/')}/healthz"
    flatten = f"{args.base}/flatten"
    print(f"[watchdog] polling {health} every {args.interval}s; failures threshold {args.failures}")
    while True:
        try:
            code, _ = get(health)
            if code == 200:
                fail = 0
            else:
                fail += 1
        except Exception:
            fail += 1
        if fail >= args.failures:
            try:
                print("[watchdog] health failed. calling /flatten")
                post(flatten)
            except Exception:
                pass
            fail = 0
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
