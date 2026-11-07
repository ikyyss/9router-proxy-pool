---
name: 9router-proxy-pool
description: Use when /proxy pool. Scrapes & adds fast 9Router proxies.
---

# 9Router Proxy Pool Updater

Scrapes, tests, adds, and rotates fast free proxies for 9Router running on `http://localhost:20128`.

## Features
- **Scrape & Sync**: Pulls latency-tested HTTPS/HTTP proxies from public fast lists (`xyzs996/free-proxy-health-list` and `monosans/proxy-list`), tests locally, and registers verified ones into 9Router.
- **Health Check**: Pings 9Router's internal `/api/proxy-pools/{id}/test` endpoint for real upstream latency.
- **Auto-Prune**: Unbinds provider connections before safely deleting slow/dead pools.
- **Round-Robin Rebinding**: Spreads provider connections (e.g. Kiro accounts) 1-to-1 across active proxy pools.

## Quick CLI Usage
From this directory:

```bash
# Sync 5 fast proxies
python proxy_pool.py sync --limit 5

# Check health & latency of existing pools
python proxy_pool.py health

# Prune pools slower than 600ms
python proxy_pool.py prune --max-latency 600

# Rebind all Kiro connections round-robin across healthy pools
python proxy_pool.py rebind --provider kiro
```

## Hermes Agent Skill Integration
To trigger within Hermes:
Use `/proxy pool` or invoke this skill whenever proxies need refreshing or health checking.
