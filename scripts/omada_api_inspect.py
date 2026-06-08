#!/usr/bin/env python3
r"""Live Omada API inspector for debugging response shapes.

Reads credentials from environment variables or a .env-style config, makes
an authenticated API call, and pretty-prints the response. Useful for
investigating field names when the OpenAPI spec differs from reality.

Usage:
    # List sites
    python scripts/omada_api_inspect.py sites

    # List devices for a site
    python scripts/omada_api_inspect.py sites/{siteId}/devices

    # Fetch device traffic stats
    python scripts/omada_api_inspect.py sites/{siteId}/statistics/devices \
        --param device_mac=AA-BB-CC-DD-EE-FF \
        --param device_type=switch \
        --param interval=hourly

Required environment variables (or set in .env at repo root):
    OMADA_API_URL       e.g. https://use1-omada-northbound.tplinkcloud.com
    OMADA_ID            omadacId value
    OMADA_CLIENT_ID
    OMADA_CLIENT_SECRET

Optional:
    OMADA_ACCESS_TOKEN  Skip token fetch if you already have a valid token
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

import aiohttp


def _load_dotenv() -> None:
    """Load key=value pairs from .env if it exists."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


async def _get_token(
    session: aiohttp.ClientSession,
    api_url: str,
    omada_id: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Fetch a fresh access token using client credentials."""
    url = f"{api_url}/openapi/authorize/token"
    payload = {
        "omadacId": omada_id,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    async with session.post(
        url,
        params={"grant_type": "client_credentials"},
        json=payload,
        ssl=False,
    ) as resp:
        data = await resp.json()
    if data.get("errorCode", -1) != 0:
        print(f"Token error: {data}", file=sys.stderr)  # noqa: T201
        sys.exit(1)
    return str(data["result"]["accessToken"])


async def _fetch(path: str, extra_params: dict[str, str], page_size: int) -> None:
    """Fetch and print the API response for the given path."""
    _load_dotenv()

    api_url = os.environ.get("OMADA_API_URL", "").rstrip("/")
    omada_id = os.environ.get("OMADA_ID", "")
    client_id = os.environ.get("OMADA_CLIENT_ID", "")
    client_secret = os.environ.get("OMADA_CLIENT_SECRET", "")
    access_token = os.environ.get("OMADA_ACCESS_TOKEN", "")

    if not api_url or not omada_id:
        print(  # noqa: T201
            "OMADA_API_URL and OMADA_ID must be set.\n"
            "Export them or add to a .env file at the repo root.",
            file=sys.stderr,
        )
        sys.exit(1)

    async with aiohttp.ClientSession() as session:
        if not access_token:
            if not client_id or not client_secret:
                print(  # noqa: T201
                    "Set OMADA_ACCESS_TOKEN or both OMADA_CLIENT_ID and OMADA_CLIENT_SECRET.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print("Fetching access token...", file=sys.stderr)  # noqa: T201
            access_token = await _get_token(
                session, api_url, omada_id, client_id, client_secret
            )

        headers = {"Authorization": f"AccessToken={access_token}"}

        # Expand {omadacId} placeholder in path
        resolved_path = path.replace("{omadacId}", omada_id)
        url = f"{api_url}/openapi/v1/{omada_id}/{resolved_path.lstrip('/')}"

        all_items: list[object] = []
        page = 1

        print(f"GET {url}", file=sys.stderr)  # noqa: T201

        while True:
            params: dict[str, str | int] = {"pageSize": page_size, "page": page}
            params.update(extra_params)

            async with session.get(
                url, headers=headers, params=params, ssl=False
            ) as resp:
                data = await resp.json()

            if data.get("errorCode", -1) != 0:
                print(json.dumps(data, indent=2))  # noqa: T201
                return

            result = data.get("result", {})

            # Handle both list and paginated dict responses.
            if isinstance(result, list):
                print(json.dumps(result, indent=2))  # noqa: T201
                return

            items = result.get("data", result)
            total = result.get(
                "totalRows", len(items) if isinstance(items, list) else 1
            )

            if isinstance(items, list):
                all_items.extend(items)
                print(  # noqa: T201
                    f"  Page {page}: {len(items)} items "
                    f"(total {total}, fetched {len(all_items)})",
                    file=sys.stderr,
                )
                if len(all_items) >= total or len(items) < page_size:
                    break
                page += 1
            else:
                # Non-paginated single object.
                print(json.dumps(result, indent=2))  # noqa: T201
                return

        print(json.dumps(all_items, indent=2))  # noqa: T201


def main() -> None:
    """Entry point for the Omada API inspector CLI."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        help="API path relative to /openapi/v1/{omadacId}/ (e.g. sites, sites/{siteId}/devices)",
    )
    parser.add_argument(
        "--param",
        "-p",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        help="Extra query parameters (repeatable). E.g. --param device_type=switch",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="Items per page for paginated endpoints (default: 1000)",
    )
    args = parser.parse_args()

    extra: dict[str, str] = {}
    for kv in args.param:
        if "=" not in kv:
            print(  # noqa: T201
                f"Invalid --param format (expected KEY=VALUE): {kv}",
                file=sys.stderr,
            )
            sys.exit(1)
        k, _, v = kv.partition("=")
        extra[k.strip()] = v.strip()

    asyncio.run(_fetch(args.path, extra, args.page_size))


if __name__ == "__main__":
    main()
