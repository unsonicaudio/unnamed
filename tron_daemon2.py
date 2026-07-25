#!/usr/bin/env python3
"""
Tron Net Daemon (TronNet0):

- Exposes a WebSocket control plane for the Tron browser app.
- Maintains a virtual "network adapter" (TronNet0) that all Tron traffic
  conceptually flows through.
- Handles shell-like commands from Tron:
    - status, find, scan, cd, ls, curl, send
    - adapter_status, adapter_up, adapter_down
- Logs IP statistics (download/upload) with optional WHOIS.
- Saves stats as #0.json and can push them back to Tron as "ip_stats".

Run with:
    python tron_net_daemon.py
"""

import asyncio
import json
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import websockets
import requests

try:
    import whois
except ImportError:
    whois = None

# ------------------- Virtual adapter definition ------------------- #

class TronAdapter:
    """
    Lightweight "virtual network adapter".
    This does NOT create a real OS NIC; it models state for Tron.
    """
    def __init__(self, name="TronNet0", ip="10.66.0.1", subnet="10.66.0.0/24"):
        self.name = name
        self.ip = ip
        self.subnet = subnet
        self.state = "down"           # "up" | "down"
        self.connected_clients = 0
        self.last_state_change = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def bring_up(self):
        self.state = "up"
        self.last_state_change = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def bring_down(self):
        self.state = "down"
        self.last_state_change = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def as_dict(self):
        return {
            "name": self.name,
            "ip": self.ip,
            "subnet": self.subnet,
            "state": self.state,
            "connected_clients": self.connected_clients,
            "last_state_change": self.last_state_change,
        }


ADAPTER = TronAdapter(name="TronNet0", ip="10.66.0.1", subnet="10.66.0.0/24")

# ------------------- File / IP stats state ------------------- #

BASE_DIR = Path.cwd()
CWD = BASE_DIR

IP_STATS = {}  # ip -> stat dict
COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 465, 993, 995]
STATS_FILE = Path("#0.json")


def update_ip_stat(ip: str, direction: str):
    """
    direction: "download" or "upload"
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = IP_STATS.get(ip)
    if not entry:
        entry = {
            "ip": ip,
            "whois_name": None,
            "download_count": 0,
            "upload_count": 0,
            "last_seen": now,
        }
        IP_STATS[ip] = entry
        entry["whois_name"] = resolve_whois_name(ip)
    else:
        entry["last_seen"] = now

    if direction == "download":
        entry["download_count"] += 1
    elif direction == "upload":
        entry["upload_count"] += 1


def resolve_whois_name(ip: str):
    if whois is None:
        return None
    try:
        w = whois.whois(ip)
        candidate = w.get("org") or w.get("netname") or w.get("name")
        if isinstance(candidate, list):
            candidate = candidate[0]
        return str(candidate) if candidate else None
    except Exception:
        return None


def save_ip_stats():
    data = {
        "ips": list(IP_STATS.values()),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    STATS_FILE.write_text(json.dumps(data, indent=2))


async def send_ip_stats(ws):
    save_ip_stats()
    await ws.send(json.dumps({
        "type": "ip_stats",
        "stats": {
            "ips": list(IP_STATS.values())
        }
    }))

def log_website_access(ip: str, host: str, url: str, status: int, method: str):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    entry = IP_STATS.get(ip)
    if not entry:
        # initialize if missing
        entry = {
            "ip": ip,
            "whois_name": None,
            "download_count": 0,
            "upload_count": 0,
            "last_seen": now,
            "web_log": []   # <--- NEW LIST
        }
        IP_STATS[ip] = entry

    if "web_log" not in entry:
        entry["web_log"] = []

    entry["web_log"].append({
        "timestamp": now,
        "hostname": host,
        "url": url,
        "method": method,
        "status": status
    })

# ------------------- Command handlers ------------------- #

async def handle_find(query: str):
    results = []
    pattern = query or "*"
    for p in BASE_DIR.rglob(pattern):
        if p.is_file():
            results.append(str(p.relative_to(BASE_DIR)))
    return results


async def handle_scan(target: str):
    try:
        ip = socket.gethostbyname(target)
    except socket.gaierror:
        return [], None

    open_ports = []
    for port in COMMON_PORTS:
        try:
            with socket.create_connection((ip, port), timeout=0.3):
                open_ports.append(port)
        except OSError:
            continue
    return open_ports, ip


async def handle_ls(path: str | None):
    global CWD
    if path:
        candidate = (CWD / path).resolve()
    else:
        candidate = CWD
    if not candidate.is_dir() or not str(candidate).startswith(str(BASE_DIR)):
        return [], str(CWD)

    entries = []
    for entry in sorted(candidate.iterdir()):
        name = entry.name + ("/" if entry.is_dir() else "")
        entries.append(name)
    return entries, str(candidate)


async def handle_cd(path: str):
    global CWD
    candidate = (CWD / path).resolve()
    if not candidate.is_dir() or not str(candidate).startswith(str(BASE_DIR)):
        return str(CWD)
    CWD = candidate
    return str(CWD)


async def handle_curl(method: str, url: str):
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("Invalid URL (no hostname)")

    ip = socket.gethostbyname(host)

    # (1) count download use
    update_ip_stat(ip, "download")

    # (2) perform request
    resp = requests.request(method=method or "GET", url=url, timeout=10)

    # (3) NEW: log the hostname + URL + status code
    log_website_access(
        ip=ip,
        host=host,
        url=url,
        status=resp.status_code,
        method=method
    )

    return {
        "status_code": resp.status_code,
        "url": url,
        "hostname": host,
        "ip": ip,
        "content_preview": resp.text[:200]
    }


# ------------------- WebSocket client handler ------------------- #

async def handle_client(ws):
    """
    Main control-plane handler for Tron’s WebSocket connection.
    """
    print("[TronNet] Client connected")
    # Count this as a "client" on the adapter while connected.
    ADAPTER.connected_clients += 1
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON"
                }))
                continue

            mtype = msg.get("type")

            # --- Adapter control ---
            if mtype == "adapter_status":
                await ws.send(json.dumps({
                    "type": "adapter_status",
                    "adapter": ADAPTER.as_dict()
                }))

            elif mtype == "adapter_up":
                ADAPTER.bring_up()
                await ws.send(json.dumps({
                    "type": "adapter_status",
                    "adapter": ADAPTER.as_dict(),
                    "message": "TronNet0 brought UP."
                }))

            elif mtype == "adapter_down":
                ADAPTER.bring_down()
                await ws.send(json.dumps({
                    "type": "adapter_status",
                    "adapter": ADAPTER.as_dict(),
                    "message": "TronNet0 brought DOWN."
                }))

            # --- Existing status / IP stats ---
            elif mtype == "status":
                await ws.send(json.dumps({
                    "type": "status",
                    "cwd": str(CWD),
                    "ip_count": len(IP_STATS),
                    "adapter": ADAPTER.as_dict(),
                }))
                await send_ip_stats(ws)

            # --- File / search commands ---
            elif mtype == "find":
                query = msg.get("query") or "*"
                results = await handle_find(query)
                await ws.send(json.dumps({
                    "type": "find_result",
                    "query": query,
                    "result": results
                }))

            elif mtype == "scan":
                target = msg.get("target", "")
                open_ports, ip = await handle_scan(target)
                if ip:
                    update_ip_stat(ip, "upload")
                    await send_ip_stats(ws)
                await ws.send(json.dumps({
                    "type": "scan_result",
                    "target": target,
                    "ip": ip,
                    "open_ports": open_ports
                }))

            elif mtype == "ls":
                entries, cwd = await handle_ls(msg.get("path"))
                await ws.send(json.dumps({
                    "type": "ls_result",
                    "entries": entries,
                    "cwd": cwd
                }))

            elif mtype == "cd":
                cwd = await handle_cd(msg.get("path", ""))
                await ws.send(json.dumps({
                    "type": "cd_result",
                    "cwd": cwd
                }))

            # --- Network calls through TronNet0 ---
            elif mtype == "curl":
                method = (msg.get("method") or "GET").upper()
                url = msg.get("url", "")
                try:
                    result = await handle_curl(method, url)
                    await send_ip_stats(ws)
                    await ws.send(json.dumps({
                        "type": "curl_result",
                        **result
                    }))
                except Exception as e:
                    await ws.send(json.dumps({
                        "type": "error",
                        "message": f"curl failed: {e}"
                    }))

            elif mtype == "scan":
                # already covered above, but left in case
                pass

            elif mtype == "send":
                await ws.send(json.dumps({
                    "type": "send_ack",
                    "message": f"Payload received ({len(msg.get('payload',''))} bytes)"
                }))

            # placeholder: dial / route / learn can be handled here later
            elif mtype in ("dial", "route", "learn"):
                await ws.send(json.dumps({
                    "type": "message",
                    "message": f"Command {mtype} acknowledged (no backend action yet)."
                }))

            else:
                await ws.send(json.dumps({
                    "type": "error",
                    "message": f"Unknown command type: {mtype}"
                }))

    except websockets.exceptions.ConnectionClosedError:
        print("[TronNet] Client disconnected (error)")
    except websockets.exceptions.ConnectionClosedOK:
        print("[TronNet] Client disconnected (ok)")
    finally:
        ADAPTER.connected_clients = max(0, ADAPTER.connected_clients - 1)


async def main():
    async with websockets.serve(handle_client, "127.0.0.1", 8765):
        print("[TronNet] Listening on ws://127.0.0.1:8765  (TronNet0 control plane)")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
