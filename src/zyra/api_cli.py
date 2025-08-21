from __future__ import annotations

import argparse
import json
import os
import sys
import time


def _base_url(v: str | None) -> str:
    return (v or os.environ.get("DVH_BASE_URL") or "http://localhost:8000").rstrip("/")


def cmd_upload(args: argparse.Namespace) -> int:
    import requests  # type: ignore

    url = _base_url(args.base_url) + "/upload"
    from pathlib import Path

    p = Path(args.file)
    with p.open("rb") as f:
        files = {"file": (p.name, f)}
        r = requests.post(url, files=files, timeout=60)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


def _stream_ws(job_id: str, base: str, stream: str | None = None) -> None:
    try:
        import websockets  # type: ignore
    except Exception:
        print("websockets not installed; falling back to polling", file=sys.stderr)
        _poll(job_id, base)
        return
    import asyncio

    async def main():
        url = f"{base.replace('http','ws')}/ws/jobs/{job_id}"
        if stream:
            url += f"?stream={stream}"
        async with websockets.connect(url) as ws:
            async for msg in ws:
                print(msg)

    asyncio.run(main())


def _poll(job_id: str, base: str, interval: float = 1.0) -> None:
    import requests  # type: ignore

    url = f"{base}/jobs/{job_id}"
    while True:
        r = requests.get(url, timeout=30)
        if r.status_code >= 400:
            print(r.text, file=sys.stderr)
            return
        js = r.json()
        print(json.dumps(js))
        if js.get("status") in {"succeeded", "failed", "canceled"}:
            return
        time.sleep(interval)


def cmd_run(args: argparse.Namespace) -> int:
    import requests  # type: ignore

    base = _base_url(args.base_url)
    body = None
    if args.body:
        body = json.loads(args.body)
    else:
        body = {
            "stage": args.stage,
            "command": args.command,
            "mode": args.mode,
            "args": json.loads(args.args or "{}"),
        }
    r = requests.post(f"{base}/cli/run", json=body, timeout=60)
    r.raise_for_status()
    js = r.json()
    print(json.dumps(js, indent=2))
    job_id = js.get("job_id")
    if args.ws and job_id:
        _stream_ws(job_id, base, args.stream)
    elif args.poll and job_id:
        _poll(job_id, base)
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    import requests  # type: ignore

    base = _base_url(args.base_url)
    params = {}
    if args.file:
        params["file"] = args.file
    if args.zip:
        params["zip"] = 1
    url = f"{base}/jobs/{args.job_id}/download"
    from pathlib import Path

    with requests.get(url, params=params, stream=True, timeout=60) as r:
        r.raise_for_status()
        name = args.output or r.headers.get(
            "Content-Disposition", "attachment; filename=output.bin"
        ).split("filename=")[-1].strip().strip('"')
        with Path(name).open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
        print(name)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="zyra-cli", description="Simple CLI wrapper for the Zyra API"
    )
    p.add_argument(
        "--base-url",
        dest="base_url",
        help="API base URL (default http://localhost:8000)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload", help="Upload a file")
    up.add_argument("file")
    up.set_defaults(func=cmd_upload)

    rn = sub.add_parser("run", help="Run a CLI request")
    rn.add_argument("--body", help="Full JSON body string for /cli/run")
    rn.add_argument("--stage")
    rn.add_argument("--command")
    rn.add_argument("--mode", default="sync")
    rn.add_argument("--args", help="JSON for args map")
    rn.add_argument("--ws", action="store_true", help="WebSocket stream if async")
    rn.add_argument(
        "--stream", help="Comma-separated WS filters: stdout,stderr,progress"
    )
    rn.add_argument("--poll", action="store_true", help="HTTP poll if async")
    rn.set_defaults(func=cmd_run)

    dl = sub.add_parser("download", help="Download job artifact")
    dl.add_argument("job_id")
    dl.add_argument("-o", "--output", help="Output filename")
    dl.add_argument("--file", help="Specific file from manifest")
    dl.add_argument("--zip", action="store_true", help="Zip on demand")
    dl.set_defaults(func=cmd_download)

    ns = p.parse_args(argv)
    return int(ns.func(ns) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
