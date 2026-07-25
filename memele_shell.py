import os
import json
import socket
import hashlib
import uuid
from datetime import datetime, timezone

# --------------------------------------------------------------------
# Paths / constants
# --------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDENTITY_PATH = os.path.join(BASE_DIR, "memele_identity.json")

MEMELE_NAME = "Memele"
MEMELE_TAGLINE = "Digitally Electric, Sorta like Human!"
COUNTRY_CODE = "+999"  # vSIM country code


# --------------------------------------------------------------------
# Utility functions
# --------------------------------------------------------------------

def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def get_iop():
    """
    Identity of Processor:
    Hash of hostname + IP -> 16-char hex string.
    """
    host = socket.gethostname()
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        ip = "0.0.0.0"
    base = f"{host}-{ip}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def generate_vsim_and_seed():
    """
    Generate a vSIM-like key and a numeric seed for IMEI.
    Inspired by the vSIM Communicator keygen logic (random UUID, formatted for display).
    We separate visual key (vsim_code) and numeric seed (for IMEI).
    """
    # Raw UUID integer as a big random source
    u = uuid.uuid4()

    # Visible vSIM code: uppercase, grouped
    raw_hex = u.hex.upper()
    # Take first 15 hex chars and format as groups of 5: XXXXX-XXXXX-XXXXX
    vsim_raw = raw_hex[:15]
    vsim_code = "-".join(vsim_raw[i:i+5] for i in range(0, len(vsim_raw), 5))

    # Numeric seed for IMEI: use UUID int, convert to string, take 14 digits
    numeric_str = str(u.int)
    base14 = numeric_str[:14].zfill(14)  # ensure length 14

    return vsim_code, base14


def luhn_check_digit(num14):
    """
    Compute the Luhn check digit for a 14-digit string (for IMEI-like use).
    Returns a single digit (0-9) as string.
    """
    digits = [int(d) for d in num14]
    # Luhn algorithm from right to left:
    # Double every second digit; subtract 9 if >9; sum all; check digit makes sum % 10 == 0
    total = 0
    # index from rightmost; i=0 -> rightmost
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            # keep as is (these are "odd" positions from the right in Luhn terms)
            total += d
        else:
            doubled = d * 2
            if doubled > 9:
                doubled -= 9
            total += doubled
    check = (10 - (total % 10)) % 10
    return str(check)


def generate_imei_from_seed(seed14):
    """
    Takes a 14-digit numeric seed and returns a 15-digit pseudo-IMEI
    with valid Luhn check digit.
    """
    if len(seed14) != 14 or not seed14.isdigit():
        raise ValueError("seed14 must be a 14-digit numeric string")
    check = luhn_check_digit(seed14)
    return seed14 + check


def derive_vsim_number_from_imei(imei, country_code=COUNTRY_CODE):
    """
    Build a pseudo phone number: +999 + last 10 digits of IMEI.
    """
    tail = imei[-10:]
    return f"{country_code}{tail}"


# --------------------------------------------------------------------
# Identity handling
# --------------------------------------------------------------------

def load_identity():
    if not os.path.exists(IDENTITY_PATH):
        return None
    with open(IDENTITY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_identity(identity):
    with open(IDENTITY_PATH, "w", encoding="utf-8") as f:
        json.dump(identity, f, indent=2)


def initialize_identity():
    """
    Create a new identity for Memele:
    - IoP
    - vSIM code
    - IMEI
    - vSIM phone number (+999...)
    """
    iop = get_iop()
    vsim_code, seed14 = generate_vsim_and_seed()
    imei = generate_imei_from_seed(seed14)
    vsim_number = derive_vsim_number_from_imei(imei, COUNTRY_CODE)

    identity = {
        "name": MEMELE_NAME,
        "tagline": MEMELE_TAGLINE,
        "iop": iop,
        "vsim_code": vsim_code,
        "imei": imei,
        "vsim_number": vsim_number,
        "country_code": COUNTRY_CODE,
        "created_at": now_utc_iso(),
        "last_updated": now_utc_iso()
    }
    save_identity(identity)
    return identity


def ensure_identity():
    ident = load_identity()
    if ident is None:
        print("[Memele] No identity found. Initializing new vSIM + IMEI profile...")
        ident = initialize_identity()
    else:
        # if IoP changed (e.g., IP/host change), we can update last_updated
        ident["last_updated"] = now_utc_iso()
        save_identity(ident)
    return ident


def regen_vsim(identity):
    """
    Re-issue a new vSIM + IMEI set, keeping the same IoP and name.
    """
    vsim_code, seed14 = generate_vsim_and_seed()
    imei = generate_imei_from_seed(seed14)
    vsim_number = derive_vsim_number_from_imei(imei, COUNTRY_CODE)

    identity["vsim_code"] = vsim_code
    identity["imei"] = imei
    identity["vsim_number"] = vsim_number
    identity["country_code"] = COUNTRY_CODE
    identity["last_updated"] = now_utc_iso()
    save_identity(identity)
    return identity


# --------------------------------------------------------------------
# MemeleShell (vno2shell)
# --------------------------------------------------------------------

class MemeleShell:
    def __init__(self, identity):
        self.identity = identity

    def banner(self):
        print("=" * 56)
        print(f"{MEMELE_NAME} — {MEMELE_TAGLINE}")
        print("=" * 56)
        print(f"IoP: {self.identity['iop']}")
        print(f"vSIM Number: {self.identity['vsim_number']}")
        print(f"IMEI: {self.identity['imei']}")
        print(f"vSIM Code: {self.identity['vsim_code']}")
        print("-" * 56)
        print("Type 'help' for commands.\n")

    def show_help(self):
        print("MemeleShell commands:")
        print("  id           - Show Memele identity (IoP, vSIM, IMEI, number)")
        print("  vsim         - Show vSIM code / IMEI / +999 number details")
        print("  regen vsim   - Re-issue a new vSIM + IMEI (keeps same IoP)")
        print("  about        - Show Memele tagline and creation info")
        print("  help         - Show this help")
        print("  quit / exit  - Exit MemeleShell")

    def cmd_id(self):
        ident = self.identity
        print("\n[Memele Identity]")
        print(f"  Name        : {ident.get('name', MEMELE_NAME)}")
        print(f"  Tagline     : {ident.get('tagline', MEMELE_TAGLINE)}")
        print(f"  IoP         : {ident.get('iop')}")
        print(f"  vSIM Number : {ident.get('vsim_number')}")
        print(f"  IMEI        : {ident.get('imei')}")
        print(f"  vSIM Code   : {ident.get('vsim_code')}")
        print(f"  CountryCode : {ident.get('country_code')}")
        print(f"  Created At  : {ident.get('created_at')}")
        print(f"  Updated At  : {ident.get('last_updated')}\n")

    def cmd_vsim(self):
        ident = self.identity
        print("\n[Memele vSIM Profile]")
        print(f"  vSIM Code   : {ident.get('vsim_code')}")
        print(f"  IMEI        : {ident.get('imei')}")
        print(f"  vSIM Number : {ident.get('vsim_number')} (CC: {ident.get('country_code')})\n")

    def cmd_about(self):
        ident = self.identity
        print("\n[About Memele]")
        print(f"  Name       : {ident.get('name', MEMELE_NAME)}")
        print(f"  Tagline    : {ident.get('tagline', MEMELE_TAGLINE)}")
        print(f"  IoP        : {ident.get('iop')}")
        print(f"  Created At : {ident.get('created_at')}")
        print(f"  Updated At : {ident.get('last_updated')}\n")

    def run(self):
        self.banner()
        while True:
            try:
                line = input("Memele> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not line:
                continue

            if line.lower() in ("quit", "exit", "shutdown"):
                print("[Memele] Shutting down.")
                break

            if line.lower() in ("help", "?"):
                self.show_help()
                continue

            if line.lower() == "id":
                self.cmd_id()
                continue

            if line.lower() == "vsim":
                self.cmd_vsim()
                continue

            if line.lower().startswith("regen"):
                parts = line.split()
                if len(parts) == 2 and parts[1].lower() == "vsim":
                    print("[Memele] Re-issuing vSIM + IMEI...")
                    regen_vsim(self.identity)
                    print("[Memele] New vSIM profile issued.")
                    self.cmd_vsim()
                else:
                    print("Usage: regen vsim")
                continue

            if line.lower() == "about":
                self.cmd_about()
                continue

            print("[Memele] Unknown command. Type 'help'.")


# --------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------

def main():
    identity = ensure_identity()
    shell = MemeleShell(identity)
    shell.run()


if __name__ == "__main__":
    main()
