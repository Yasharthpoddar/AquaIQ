"""Immutable bounded official-source retrieval; never writes outside a new research run."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import ssl
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ALLOWED = {"nwdp.nwic.gov.in", "www.nwdp.nwic.gov.in", "cgwb.gov.in", "www.cgwb.gov.in", "gwdata.cgwb.gov.in"}


def fetch(url, destination, maximum_bytes=32_000_000, sample_bytes=None):
    destination = Path(destination).resolve()
    run = Path(__file__).resolve().parent
    if not destination.is_relative_to(run) or destination == run:
        raise ValueError("All downloads must stay inside this new research report directory")
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in ALLOWED:
        raise ValueError("Only allowlisted official HTTPS sources may be retrieved")
    sidecar = destination.with_suffix(destination.suffix + ".retrieval.json")
    if destination.exists() or sidecar.exists():
        raise FileExistsError("Retained downloads and retrieval records are immutable; choose a new name")
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    request = Request(url, headers={"User-Agent": "AquaIQ-academic-research/1.0", **({"Range": f"bytes=0-{sample_bytes-1}"} if sample_bytes else {})})
    data = bytearray()
    with urlopen(request, timeout=90, context=ssl.create_default_context()) as response:
        if urlparse(response.url).hostname not in ALLOWED:
            raise ValueError("Unexpected redirect away from official source")
        headers = dict(response.headers.items())
        status = response.status
        length = response.headers.get("Content-Length")
        if not sample_bytes and length and int(length) > maximum_bytes:
            raise ValueError(f"Response exceeds approved bounded size: {length}")
        limit = min(maximum_bytes, sample_bytes) if sample_bytes else maximum_bytes
        while len(data) < limit:
            chunk = response.read(min(65536, limit-len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if not sample_bytes and response.read(1):
            raise ValueError("Response exceeds bounded size; nothing saved")
        final_url = response.url
    metadata = {"requested_url": url, "final_url": final_url, "started_at_utc": started,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "http_status": status,
                "headers": headers, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "sample_only": bool(sample_bytes), "sample_byte_limit": sample_bytes,
                "availability_caveat": "Retrieval now is not evidence of publication or availability at historical origins."}
    with destination.open("xb") as handle:
        handle.write(data)
    with sidecar.open("x", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
    print(json.dumps({"path": str(destination), "bytes": len(data), "sha256": metadata["sha256"], "sample_only": bool(sample_bytes)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("destination")
    parser.add_argument("--max-bytes", type=int, default=32_000_000)
    parser.add_argument("--sample-bytes", type=int)
    args = parser.parse_args()
    fetch(args.url, args.destination, args.max_bytes, args.sample_bytes)
