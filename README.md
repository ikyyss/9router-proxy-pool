# 9Router Proxy Pool Manager

Automated proxy pool scraper, health checker, and connection rotator for [9Router](https://github.com/9router/9router).

Scrapes fast public HTTP/HTTPS proxies, runs parallel latency pre-tests, adds verified nodes to 9Router, and enables 1-to-1 round-robin rotation for provider accounts (such as Kiro / AWS Builder ID).

Stdlib-only: **no external Python dependencies needed**.

---

## 🚀 Features

- **Automated Sync**: Scrapes from curated low-latency proxy lists (`xyzs996/free-proxy-health-list`, `monosans/proxy-list`).
- **Parallel Latency Testing**: Tests 30+ proxies concurrently against Cloudflare trace (`https://1.1.1.1/cdn-cgi/trace`).
- **9Router Verification**: Confirms proxy viability directly through 9Router's internal `/api/proxy-pools/{id}/test` endpoint; auto-deletes failing proxies.
- **Health Dashboard**: CLI view of all existing proxy pools and their measured 9Router latencies.
- **Smart Prune**: Unbinds provider accounts before deleting slow/dead pools to prevent 409 Conflict errors.
- **Connection Rotation**: Evenly distributes provider connections (e.g. Kiro accounts) across active healthy proxy pools.

---

## 📋 Requirements

- Python 3.10+ (Standard library only)
- [9Router](https://github.com/9router/9router) running locally (default: `http://localhost:20128`)

---

## 🛠️ Usage

### 1. Sync & Add Fast Proxies
Scrapes public lists, filters by latency, and registers top working proxies to 9Router:
```bash
python proxy_pool.py sync --limit 5
```

### 2. Check Pool Health & Latency
Runs 9Router's internal latency test on all saved pools and prints a table:
```bash
python proxy_pool.py health
```

### 3. Prune Slow / Dead Pools
Removes proxies exceeding the latency threshold (default 800ms) or failing tests:
```bash
python proxy_pool.py prune --max-latency 600
```
*Note: Provider connections bound to slow pools are automatically rebound to a healthy fallback pool before deletion.*

### 4. Rebind Provider Accounts (Round-Robin)
Distributes accounts across active proxy pools:
```bash
python proxy_pool.py rebind --provider kiro
```

---

## ⚙️ Options & Environment Variables

| Argument | Env Variable | Default | Description |
|---|---|---|---|
| `--router-url` | `ROUTER_URL` | `http://localhost:20128` | 9Router base URL |
| `--limit` | — | `5` | Number of fast proxies to add during `sync` |
| `--max-latency` | — | `800` | Max latency threshold (ms) for `prune` |
| `--provider` | — | `kiro` | Provider slug for `rebind` |

---

## 🤖 Hermes Agent Skill

This repository can also be used as a Hermes Agent skill.
Copy `SKILL.md` to your Hermes skills directory:
```bash
# Example Windows path:
# %APPDATA%\hermes\skills\9router-proxy-pool\SKILL.md
```
Trigger via `/proxy pool` in chat.

---

## 📄 License

MIT License. See `LICENSE`.
