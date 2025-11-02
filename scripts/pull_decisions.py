import argparse
import os
import sys
import urllib.request


def get(url: str) -> bytes:
    with urllib.request.urlopen(url) as r:
        return r.read()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="http://127.0.0.1:8080", help="Base URL of the API")
    p.add_argument("--out", default="exports_download", help="Output directory")
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    base = args.host.rstrip("/")
    endpoints = {
        "decisions.csv": f"{base}/export/decisions.csv",
        "decisions.schema.json": f"{base}/export/decisions.schema.json",
    }
    for filename, url in endpoints.items():
        try:
            data = get(url)
            path = os.path.join(args.out, filename)
            with open(path, "wb") as f:
                f.write(data)
            print(f"Saved {filename} from {url}")
        except Exception as e:
            print(f"Failed {url}: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
