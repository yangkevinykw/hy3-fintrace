"""Download public FinQA artifacts pinned to an immutable revision."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0f16e2867befa6840783e58be38c9efb9229d742"
HASHES = {"dataset/train.json": "49f237eb9779b569473b26b08048867d04635a7cc39ad6a7a5664c55bb428db6",
          "code/evaluate/evaluate.py": "845cd131cab843eceff256cf6d392978cc470a7da4a80107beb56027fdca5c13",
          "LICENSE": "92c0e67bd762c15c07ba60de09558338315a8ebf99aac4f51f487179809ac087"}


def main():
    cache = ROOT / "data/cache"
    cache.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ["dataset/train.json", "code/evaluate/evaluate.py", "LICENSE"]:
        dest = cache / name.replace("/", "_")
        url = f"https://raw.githubusercontent.com/czyssrs/FinQA/{REVISION}/{name}"
        if not dest.exists():
            with urllib.request.urlopen(url, timeout=180) as response:
                payload = response.read()
            if hashlib.sha256(payload).hexdigest() != HASHES[name]:
                raise ValueError(f"Source hash mismatch: {name}")
            dest.write_bytes(payload)
        payload = dest.read_bytes()
        if hashlib.sha256(payload).hexdigest() != HASHES[name]:
            raise ValueError(f"Cached file hash mismatch: {dest.name}; re-download the pinned source")
        records.append({"path": name, "url": url, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
        print(name, len(payload), flush=True)
    (cache / "download_manifest.json").write_text(json.dumps({"revision": REVISION, "files": records}, indent=2), encoding="utf-8")
    raw = json.loads((cache / "dataset_train.json").read_text(encoding="utf-8"))
    for row in raw[:4]:
        print(json.dumps({"id": row["id"], "qa": row["qa"], "table": row["table"]}, ensure_ascii=False)[:3500])


if __name__ == "__main__":
    main()
