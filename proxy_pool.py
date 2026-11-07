#!/usr/bin/env python3
"""9Router Proxy Pool Manager

Scrapes, tests, adds, and rotates fast proxies for 9Router.
Stdlib-only (no third-party dependencies required).

Usage:
    python proxy_pool.py sync [--limit 5] [--router-url http://localhost:20128]
    python proxy_pool.py health [--router-url http://localhost:20128]
    python proxy_pool.py prune [--max-latency 800] [--router-url http://localhost:20128]
    python proxy_pool.py rebind [--provider kiro] [--router-url http://localhost:20128]
"""

import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_ROUTER = os.environ.get("ROUTER_URL", "http://localhost:20128").rstrip("/")

SOURCES = [
    "https://raw.githubusercontent.com/xyzs996/free-proxy-health-list/main/proxies/latency/fast/data.json",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt",
]


def make_request(url, data=None, headers=None, method="GET", timeout=10):
    if headers is None:
        headers = {}
    if data is not None and isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_proxy_latency(proxy_url, timeout=1.5):
    """Test raw proxy connection latency via Cloudflare trace."""
    t0 = time.time()
    try:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(handler)
        req = urllib.request.Request(
            "https://1.1.1.1/cdn-cgi/trace", headers={"User-Agent": "curl/7.68.0"}
        )
        with opener.open(req, timeout=timeout) as res:
            if res.status == 200:
                return round((time.time() - t0) * 1000)
    except Exception:
        pass
    return None


def fetch_candidates():
    candidates = []
    # Source 1: xyzs996 fast list
    try:
        req = urllib.request.Request(SOURCES[0], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode("utf-8"))
            fast_https = [
                x
                for x in data
                if x.get("supportsHttps") and x.get("protocol") in ("http", "https")
            ]
            fast_https.sort(key=lambda x: x.get("latencyMs", 99999))
            for x in fast_https[:40]:
                candidates.append(
                    (f"http://{x['proxy']}", f"{x.get('country', 'fast')}-{x['proxy']}")
                )
    except Exception as e:
        print(f"[!] Warning: failed fetching source 1: {e}", file=sys.stderr)

    # Source 2: monosans proxy list
    try:
        req = urllib.request.Request(SOURCES[1], headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            lines = [l.strip().decode() for l in r.readlines() if l.strip()][:40]
            for l in lines:
                p = l if l.startswith("http") else f"http://{l}"
                candidates.append((p, f"monosans-{l}"))
    except Exception as e:
        print(f"[!] Warning: failed fetching source 2: {e}", file=sys.stderr)

    # Deduplicate
    seen = set()
    uniq = []
    for u, n in candidates:
        if u not in seen:
            seen.add(u)
            uniq.append((u, n))
    return uniq


def cmd_sync(router_url, limit):
    print(f"[*] Checking 9Router at {router_url}...")
    try:
        res = make_request(f"{router_url}/api/proxy-pools", timeout=4)
        existing = {p["proxyUrl"] for p in res.get("proxyPools", [])}
    except Exception as e:
        print(f"[!] Error: 9Router is offline or unreachable ({e})", file=sys.stderr)
        sys.exit(1)

    print("[*] Fetching candidates from public fast proxy sources...")
    candidates = [c for c in fetch_candidates() if c[0] not in existing]
    print(f"[*] Found {len(candidates)} new candidates. Testing latency concurrently...")

    alive = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as ex:
        futs = {ex.submit(test_proxy_latency, u): (u, n) for u, n in candidates}
        for f in concurrent.futures.as_completed(futs):
            ms = f.result()
            if ms:
                u, n = futs[f]
                alive.append((u, n, ms))

    alive.sort(key=lambda x: x[2])
    print(f"[*] {len(alive)} proxies responded locally. Adding to 9Router...")

    added = 0
    for u, n, pre_ms in alive[:15]:
        payload = {
            "name": f"{n} ({pre_ms}ms)",
            "proxyUrl": u,
            "type": "http",
            "strictProxy": False,
        }
        try:
            res = make_request(
                f"{router_url}/api/proxy-pools", data=payload, method="POST", timeout=5
            )
            pid = res["proxyPool"]["id"]
            tres = make_request(
                f"{router_url}/api/proxy-pools/{pid}/test", data={}, method="POST", timeout=7
            )
            if tres.get("ok"):
                elapsed = tres.get("elapsedMs")
                print(f"  [+] Added: {n} | 9Router latency: {elapsed}ms")
                added += 1
                if added >= limit:
                    break
            else:
                make_request(f"{router_url}/api/proxy-pools/{pid}", method="DELETE", timeout=5)
        except Exception:
            pass

    print(f"[✔] Done. Successfully added {added} verified proxies to 9Router.")


def cmd_health(router_url):
    print(f"[*] Testing health of all existing proxy pools on {router_url}...")
    try:
        res = make_request(f"{router_url}/api/proxy-pools", timeout=5)
        pools = res.get("proxyPools", [])
    except Exception as e:
        print(f"[!] Error: 9Router unreachable ({e})", file=sys.stderr)
        sys.exit(1)

    if not pools:
        print("[*] No proxy pools found.")
        return

    results = []
    for p in pools:
        pid = p["id"]
        name = p["name"]
        url = p["proxyUrl"]
        try:
            tres = make_request(
                f"{router_url}/api/proxy-pools/{pid}/test", data={}, method="POST", timeout=6
            )
            ok = tres.get("ok", False)
            elapsed = tres.get("elapsedMs", "-")
            status = "OK" if ok else "FAIL"
        except Exception:
            ok = False
            elapsed = "-"
            status = "TIMEOUT"
        results.append((name, url, elapsed, status))

    print("\n| Name | URL | 9Router Latency | Status |")
    print("|---|---|---|---|")
    for name, url, elapsed, status in results:
        print(f"| {name} | {url} | {elapsed}ms | {status} |")
    print()


def cmd_prune(router_url, max_latency):
    print(f"[*] Pruning proxies with latency > {max_latency}ms or failing status...")
    try:
        pools = make_request(f"{router_url}/api/proxy-pools", timeout=5).get("proxyPools", [])
        conns = make_request(f"{router_url}/api/providers", timeout=5).get("connections", [])
    except Exception as e:
        print(f"[!] Error: 9Router unreachable ({e})", file=sys.stderr)
        sys.exit(1)

    # Test all pools
    good_pools = []
    bad_pool_ids = set()
    for p in pools:
        pid = p["id"]
        try:
            tres = make_request(
                f"{router_url}/api/proxy-pools/{pid}/test", data={}, method="POST", timeout=6
            )
            elapsed = tres.get("elapsedMs", 99999)
            if tres.get("ok") and elapsed <= max_latency:
                good_pools.append(pid)
            else:
                bad_pool_ids.add(pid)
        except Exception:
            bad_pool_ids.add(pid)

    if not bad_pool_ids:
        print("[✔] All proxy pools are healthy. Nothing to prune.")
        return

    print(f"[*] Identified {len(bad_pool_ids)} slow/dead pools to remove.")

    # Unbind from connections referencing bad pools
    fallback_pool = good_pools[0] if good_pools else None
    for c in conns:
        cid = c.get("id")
        psdata = c.get("providerSpecificData") or {}
        bound_pool = psdata.get("proxyPoolId")
        if bound_pool in bad_pool_ids:
            psdata["proxyPoolId"] = fallback_pool
            c["providerSpecificData"] = psdata
            try:
                make_request(f"{router_url}/api/providers/{cid}", data=c, method="PUT", timeout=5)
                print(f"  [-] Unbound connection '{c.get('name')}' from pool {bound_pool}")
            except Exception as e:
                print(f"  [!] Failed to update connection {cid}: {e}", file=sys.stderr)

    # Delete bad pools
    deleted = 0
    for pid in bad_pool_ids:
        try:
            make_request(f"{router_url}/api/proxy-pools/{pid}", method="DELETE", timeout=5)
            deleted += 1
        except Exception as e:
            print(f"  [!] Failed deleting pool {pid}: {e}", file=sys.stderr)

    print(f"[✔] Successfully pruned {deleted} slow/dead pools.")


def cmd_rebind(router_url, provider_filter):
    print(f"[*] Distributing '{provider_filter}' connections across healthy proxy pools...")
    try:
        pools = make_request(f"{router_url}/api/proxy-pools", timeout=5).get("proxyPools", [])
        conns = make_request(f"{router_url}/api/providers", timeout=5).get("connections", [])
    except Exception as e:
        print(f"[!] Error: 9Router unreachable ({e})", file=sys.stderr)
        sys.exit(1)

    # Find working pools
    active_pool_ids = []
    for p in pools:
        pid = p["id"]
        try:
            tres = make_request(
                f"{router_url}/api/proxy-pools/{pid}/test", data={}, method="POST", timeout=5
            )
            if tres.get("ok"):
                active_pool_ids.append(pid)
        except Exception:
            pass

    if not active_pool_ids:
        print("[!] No active healthy proxy pools available to bind.", file=sys.stderr)
        sys.exit(1)

    matching_conns = [c for c in conns if c.get("provider") == provider_filter]
    print(
        f"[*] Found {len(matching_conns)} connections and {len(active_pool_ids)} healthy pools."
    )

    for i, c in enumerate(matching_conns):
        cid = c.get("id")
        pool_id = active_pool_ids[i % len(active_pool_ids)]
        psdata = c.get("providerSpecificData") or {}
        psdata["proxyPoolId"] = pool_id
        c["providerSpecificData"] = psdata
        try:
            make_request(f"{router_url}/api/providers/{cid}", data=c, method="PUT", timeout=5)
            print(f"  [+] Bound {c.get('name', cid)} -> pool {pool_id}")
        except Exception as e:
            print(f"  [!] Failed updating connection {cid}: {e}", file=sys.stderr)

    print("[✔] Round-robin proxy binding completed.")


def main():
    parser = argparse.ArgumentParser(description="9Router Proxy Pool Manager")
    parser.add_argument("--router-url", default=DEFAULT_ROUTER, help="9Router base URL")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # sync
    p_sync = subparsers.add_parser("sync", help="Scrape, test, and add fast proxies")
    p_sync.add_argument("--limit", type=int, default=5, help="Number of proxies to add (default 5)")

    # health
    subparsers.add_parser("health", help="Check latency of all existing pools")

    # prune
    p_prune = subparsers.add_parser("prune", help="Prune slow and dead proxies")
    p_prune.add_argument(
        "--max-latency", type=int, default=800, help="Max allowed latency in ms (default 800)"
    )

    # rebind
    p_rebind = subparsers.add_parser(
        "rebind", help="Distribute connections across pools round-robin"
    )
    p_rebind.add_argument(
        "--provider", default="kiro", help="Target provider slug (default kiro)"
    )

    args = parser.parse_args()

    if args.command == "sync":
        cmd_sync(args.router_url, args.limit)
    elif args.command == "health":
        cmd_health(args.router_url)
    elif args.command == "prune":
        cmd_prune(args.router_url, args.max_latency)
    elif args.command == "rebind":
        cmd_rebind(args.router_url, args.provider)


if __name__ == "__main__":
    main()
