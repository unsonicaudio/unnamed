#!/usr/bin/env python3
"""
Tron Virtual Modem (internalized calls + data recording)

- Purely virtual modem, no RF or direct cellular access.
- Dial:
    * Any phone-like string
    * IP (with optional leading '.' for IP mode)
- Call types:
    * internal  -> +50000 / +999 etc.
    * provider  -> numbers explicitly listed in config (legit gateways only)
    * external  -> everything else
- Optional call stream recording for your own traffic.
"""

import socket, threading, datetime, json, hashlib, os, ipaddress

LOG_DIR = "tron_logs"
CONFIG_FILE = "tron_config.json"

DEFAULT_CONFIG = {
    "listen_host": "0.0.0.0",
    "listen_port": 1,
    "modem_name": "TRON",
    "version": "2",
    "network_label": "+50000",
    "provider_numbers": [],        # e.g. ["+18885551234"]
    "internal_prefixes": ["+50000", "+999", "+1000"],
    "record_calls": True
}

def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)

def log_json(fname, payload):
    ensure_dirs()
    with open(os.path.join(LOG_DIR, fname), "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")

def log_event(event_type, data):
    payload = {
        "timestamp": datetime.datetime.now().isoformat(),
        "event": event_type,
        "data": data
    }
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"tron_{event_type}_{ts}.log"
    log_json(fname, payload)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            cfg = json.load(open(CONFIG_FILE, "r", encoding="utf-8"))
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    json.dump(DEFAULT_CONFIG, open(CONFIG_FILE, "w", encoding="utf-8"), indent=2)
    return DEFAULT_CONFIG

def classify_target(target: str) -> str:
    """Return 'ip' if target looks like an IP address, else 'number'."""
    host = target.split(":", 1)[0]
    try:
        ipaddress.ip_address(host)
        return "ip"
    except ValueError:
        return "number"

def classify_call_type(target: str, cfg) -> str:
    """internal | provider | external based on config."""
    # Provider numbers: exact match
    if target in cfg.get("provider_numbers", []):
        return "provider"
    # Internal prefixes
    for p in cfg.get("internal_prefixes", []):
        if target.startswith(p):
            return "internal"
    return "external"

class TronModemSession:
    """Handles a single TCP connection to Tron Virtual Modem."""

    def __init__(self, conn, addr, cfg):
        self.conn = conn
        self.addr = addr
        self.cfg = cfg
        self.modem_name = cfg["modem_name"]
        self.version = cfg["version"]
        self.network_label = cfg["network_label"]
        self.active_target = None
        self.active_mode = None      # 'ip' or 'number'
        self.call_type = None        # 'internal' | 'provider' | 'external'
        self.call_id = None
        self.connected = False
        self.running = True

    def send(self, text):
        try:
            self.conn.sendall((text + "\r\n").encode("ascii", errors="ignore"))
        except Exception:
            self.running = False

    def start_recording(self):
        if not self.cfg.get("record_calls", True) or not self.call_id:
            return
        log_event("call_start", {
            "from": str(self.addr),
            "target": self.active_target,
            "mode": self.active_mode,
            "call_type": self.call_type,
            "call_id": self.call_id
        })

    def record_data(self, payload: str):
        if not self.cfg.get("record_calls", True) or not self.call_id:
            return
        fname = f"tron_stream_{self.call_id}.log"
        log_json(fname, {
            "timestamp": datetime.datetime.now().isoformat(),
            "from": str(self.addr),
            "target": self.active_target,
            "call_type": self.call_type,
            "data": payload
        })

    def end_call(self):
        if self.connected and self.call_id:
            log_event("call_end", {
                "from": str(self.addr),
                "target": self.active_target,
                "mode": self.active_mode,
                "call_type": self.call_type,
                "call_id": self.call_id
            })
        self.active_target = None
        self.active_mode = None
        self.call_type = None
        self.call_id = None
        self.connected = False

    def handle_at(self, raw, upper, cmd):
        # Basic AT
        if cmd == "":
            self.send("OK")
            return

        # Reset
        if cmd == "Z":
            self.end_call()
            log_event("reset", {"addr": self.addr})
            self.send("OK")
            return

        # Info
        if cmd == "I":
            self.send(f"{self.modem_name} v{self.version} ({self.network_label})")
            self.send("OK")
            return

        # Pagetel / Mental SMS logic: AT=<logic or JSON packet>
        if cmd.startswith("="):
            eq_index = raw.find("=")
            payload_str = raw[eq_index + 1:].strip() if eq_index != -1 else ""
            
            if not payload_str:
                self.send("ERROR")
                return

            try:
                # Check if the energy packet is JSON (from Memele Mental SMS)
                if payload_str.startswith("{"):
                    packet = json.loads(payload_str)
                    event_type = "mental_sms"
                    log_data = {
                        "from": packet.get("from"),
                        "to": packet.get("to"),
                        "body": packet.get("body"),
                        "energy_signature": packet.get("metadata", {}).get("energy"),
                        "velocity": packet.get("metadata", {}).get("velocity"),
                        "session_addr": str(self.addr)
                    }
                else:
                    # Fallback for standard Pagetel logic expressions
                    event_type = "pagetel"
                    log_data = {
                        "from": str(self.addr),
                        "logic": payload_str
                    }

                log_event(event_type, log_data)
                self.send(f"OK: {event_type.upper()} RECEIVED")
                
            except Exception as e:
                log_event("modem_error", {"detail": str(e), "raw": payload_str})
                self.send("ERROR: PARSE_FAILED")
            return

        # Dial
        if cmd.startswith("D"):
            dial_raw = raw[2:].strip()
            if not dial_raw:
                self.send("ERROR")
                return

            # Leading '.' forces IP mode
            if dial_raw.startswith("."):
                target = dial_raw[1:].strip()
                mode = "ip"
            else:
                target = dial_raw
                mode = classify_target(target)

            if not target:
                self.send("ERROR")
                return

            self.call_id = hashlib.sha256(
                f"{target}-{datetime.datetime.now()}-{self.addr}".encode()
            ).hexdigest()[:16]

            self.active_target = target
            self.active_mode = mode
            self.call_type = classify_call_type(target, self.cfg)
            self.connected = True

            self.start_recording()

            log_event("dial", {
                "from": str(self.addr),
                "target": target,
                "mode": mode,
                "call_type": self.call_type,
                "call_id": self.call_id
            })

            label = "DIALING_IP" if mode == "ip" else "DIALING"
            self.send(f"{label} {target} [{self.call_type}]")
            self.send("CONNECT")
            return

        # Hang up
        if cmd == "H":
            if self.connected:
                self.end_call()
                self.send("NO CARRIER")
            else:
                self.send("OK")
            return

        # Status
        if cmd == "+STATUS":
            st = {
                "connected_to": self.active_target,
                "mode": self.active_mode,
                "call_type": self.call_type,
                "remote_addr": self.addr[0],
                "version": self.version,
                "network": self.network_label,
                "call_id": self.call_id
            }
            self.send(json.dumps(st))
            self.send("OK")
            return

        # Unknown AT
        self.send("ERROR")

    def handle(self, line):
        raw = line.strip()
        if not raw:
            return

        upper = raw.upper()

        # Data mode: if we're connected and line doesn't start with AT,
        # treat it as payload in the virtual call stream.
        if self.connected and not upper.startswith("AT"):
            self.record_data(raw)
            # You can echo or not; for now just ACK
            self.send("DATA OK")
            return

        # Normal AT command handling
        if not upper.startswith("AT"):
            self.send("ERROR")
            return

        cmd = upper[2:].strip()
        self.handle_at(raw, upper, cmd)

def session_thread(conn, addr, cfg):
    session = TronModemSession(conn, addr, cfg)
    session.send("TRON MODEM READY")

    with conn:
        while session.running:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                text = data.decode(errors="ignore")
                for part in text.split("\n"):
                    if part.strip():
                        session.handle(part)
            except Exception:
                break

def main():
    cfg = load_config()
    ensure_dirs()

    host = cfg["listen_host"]
    port = cfg["listen_port"]
    print(f"[TRON] Virtual modem listening on {host}:{port}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen()
        while True:
            conn, addr = s.accept()
            threading.Thread(target=session_thread, args=(conn, addr, cfg), daemon=True).start()

if __name__ == "__main__":
    main()
