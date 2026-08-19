"""E2E API test against real Omada controller at 192.168.0.1."""

import asyncio
import aiohttp
import json
import sys
import ssl

CONTROLLER = "192.168.0.1"
USERNAME = "bullitt"
PASSWORD = "OHkidKusdK1E!"


async def test_login_and_endpoints():
    """Login to Omada controller and test new endpoints."""
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
        # Step 1: Discover controller ID from /api/info
        print("1. Getting controller info...")
        omada_id = None
        try:
            async with session.get(
                f"https://{CONTROLLER}/api/info",
                ssl=ssl_ctx,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                raw = await resp.text()
                print(f"   Raw response: {raw[:300]}")
                info = json.loads(raw)
                # Try different field names
                omada_id = (
                    info.get("result", {}).get("omadacId")
                    or info.get("omadacId")
                    or info.get("omadaId")
                    or info.get("controllerId")
                )
                print(f"   omada_id: {omada_id}")
        except Exception as e:
            print(f"   FAILED: {e}")
            return False

        if not omada_id:
            print("   Could not discover omada_id!")
            return False

        # Step 2: Login with WebSessionAuth pattern
        print("2. Logging in...")
        csrf_token = None
        try:
            login_url = f"https://{CONTROLLER}/{omada_id}/api/v2/login"
            login_payload = {"username": USERNAME, "password": PASSWORD}
            async with session.post(
                login_url,
                json=login_payload,
                ssl=ssl_ctx,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                raw = await resp.text()
                print(f"   Raw login: {raw[:300]}")
                login_data = json.loads(raw)
                print(f"   Login result: errorCode={login_data.get('errorCode')}")
                if login_data.get("errorCode") != 0:
                    print(f"   Login FAILED: {login_data}")
                    return False
                csrf_token = login_data["result"]["token"]
                print(f"   CSRF token: {csrf_token[:20]}...")
        except Exception as e:
            print(f"   FAILED: {e}")
            return False

        # Step 3: Get sites
        print("3. Getting sites...")
        site_id = None
        try:
            sites_url = f"https://{CONTROLLER}/{omada_id}/openapi/v1/{omada_id}/sites"
            headers = {
                "Csrf-Token": csrf_token,
                "Omada-Request-Source": "web-local",
            }
            async with session.get(
                sites_url,
                headers=headers,
                ssl=ssl_ctx,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                raw = await resp.text()
                print(f"   Raw sites: {raw[:300]}")
                sites_data = json.loads(raw)
                print(f"   Sites response: errorCode={sites_data.get('errorCode')}")
                result = sites_data.get("result", {})
                sites = result.get("data", [])
                for s in sites:
                    sid = s.get("siteId", "unknown")
                    sname = s.get("name", "unknown")
                    print(f"   Site: {sname} (id={sid})")
                if sites:
                    site_id = sites[0].get("siteId")
                else:
                    print("   No sites found!")
                    return False
        except Exception as e:
            print(f"   FAILED: {e}")
            return False

        print(f"   Using site: {site_id}")

        base = f"https://{CONTROLLER}/{omada_id}"
        api_headers = {
            "Csrf-Token": csrf_token,
            "Omada-Request-Source": "web-local",
        }

        # Step 4: Test VPN endpoints
        print("4. Testing VPN status endpoints...")
        for vpn_type in ["s2s", "server", "client"]:
            try:
                url = f"{base}/openapi/v1/{omada_id}/sites/{site_id}/stats/vpn/{vpn_type}"
                async with session.get(
                    url,
                    headers=api_headers,
                    ssl=ssl_ctx,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json(content_type=None)
                    result = data.get("result", {})
                    count = len(result.get("data", [])) if isinstance(result, dict) else "N/A"
                    print(f"   VPN {vpn_type}: errorCode={data.get('errorCode')}, tunnels={count}")
                    if data.get("errorCode") == 0 and isinstance(result, dict):
                        for tunnel in result.get("data", []):
                            name = tunnel.get("name", "?")
                            status = tunnel.get("status", "?")
                            print(f"     - {name} status={status}")
            except Exception as e:
                print(f"   VPN {vpn_type}: FAILED: {e}")

        # Step 5: Test WAN speed test GET endpoint
        print("5. Testing WAN speed test GET endpoint...")
        try:
            url = f"{base}/openapi/v1/{omada_id}/sites/{site_id}/statistics/speedTest"
            async with session.get(
                url,
                headers=api_headers,
                ssl=ssl_ctx,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json(content_type=None)
                print(f"   Speed test result: errorCode={data.get('errorCode')}")
                result = data.get("result", {})
                if isinstance(result, dict):
                    for key in ["downloadSpeed", "uploadSpeed", "latency", "testTime"]:
                        print(f"   {key}: {result.get(key)}")
                else:
                    print(f"   Raw result: {json.dumps(result)[:200]}")
        except Exception as e:
            print(f"   FAILED: {e}")

        # Step 6: Test WAN speed test trigger (POST)
        print("6. Testing WAN speed test trigger endpoint (POST)...")
        try:
            url = f"{base}/openapi/v1/{omada_id}/sites/{site_id}/commands/speedTest"
            async with session.post(
                url,
                json={},
                headers=api_headers,
                ssl=ssl_ctx,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json(content_type=None)
                print(f"   Trigger result: errorCode={data.get('errorCode')}, data={json.dumps(data)[:200]}")
        except Exception as e:
            print(f"   FAILED: {e}")

        return True


if __name__ == "__main__":
    result = asyncio.run(test_login_and_endpoints())
    sys.exit(0 if result else 1)
