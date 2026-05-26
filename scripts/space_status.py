#!/usr/bin/env python3
"""Print Hugging Face Space runtime status without exposing tokens."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


API = "https://huggingface.co/api"


def request_json(url: str, token: str | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_spaces(author: str, token: str | None, include_private: bool):
    query = urllib.parse.urlencode({"author": author, "full": "false"})
    spaces = request_json(f"{API}/spaces?{query}", token if include_private else None)
    if not include_private:
        spaces = [space for space in spaces if not space.get("private")]
    return [space["id"] for space in spaces]


def get_runtime(space_id: str, token: str | None):
    return request_json(f"{API}/spaces/{space_id}/runtime", token)


def short_error(runtime: dict, limit: int = 140) -> str:
    message = runtime.get("errorMessage") or ""
    message = " ".join(str(message).split())
    return message[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", help="Hub user or organization to list Spaces for.")
    parser.add_argument("--ids", nargs="*", help="Explicit Space ids like user/space.")
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Include private Spaces when listing by --author. Requires explicit authorization and a token.",
    )
    parser.add_argument(
        "--token-env",
        default="HF_TOKEN",
        help="Environment variable containing a Hugging Face token. Default: HF_TOKEN.",
    )
    args = parser.parse_args()

    token = os.getenv(args.token_env)
    if args.include_private and not token:
        print(f"error: --include-private requires ${args.token_env}", file=sys.stderr)
        return 2

    ids = list(args.ids or [])
    if args.author:
        ids.extend(get_spaces(args.author, token, args.include_private))
    if not ids:
        print("error: pass --author or --ids", file=sys.stderr)
        return 2

    print("id\tstage\tcurrent\trequested\terror")
    for space_id in sorted(dict.fromkeys(ids)):
        try:
            runtime = get_runtime(space_id, token if token else None)
            hardware = runtime.get("hardware") or {}
            print(
                "\t".join(
                    [
                        space_id,
                        str(runtime.get("stage") or ""),
                        str(hardware.get("current") or ""),
                        str(hardware.get("requested") or ""),
                        short_error(runtime),
                    ]
                )
            )
        except urllib.error.HTTPError as exc:
            print(f"{space_id}\tHTTP_{exc.code}\t\t\t{exc.reason}")
        except Exception as exc:  # noqa: BLE001
            print(f"{space_id}\tERROR\t\t\t{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
