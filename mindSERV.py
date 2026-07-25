import uuid
import datetime
import hashlib
import os
import json
import requests
import re
import io
import contextlib
import builtins
import sys
import threading



# Security lock: disable outbound HTTP requests until reviewed
DISABLE_NETWORK = True



# --- Files / constants ---
MEMORY_FILE = "memele_identity.json"
SESSION_LOG = "session.log"
BOT_IDENTITY_FILE = "cipher.json"
OLD_MEMORY_FILE = "trose.py"
COOKIES = "cookies.json"
COOKIE_FILE = "in.json"

DIR_STACK = []




# --- Preserve original print so we can use it safely inside our wrapper ---
_original_print = builtins.print

# Thread lock so concurrent prints (if any) don't interleave in the file
_print_lock = threading.Lock()

def _write_log_line(text: str):
    """
    Write a single line to the session log with timestamp.
    Use low-level file write so we don't call print() recursively.
    """
    ts = datetime.datetime.now().isoformat()
    line = f"[{ts}] {text}\n"
    try:
        with open(SESSION_LOG, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        # If logging to file fails, still print to console using original print
        _original_print(f"[LOG WRITE ERROR] {e}")

def _print_wrapper(*args, sep=" ", end="\n", file=None, flush=False, **kwargs):
    """
    Replacement for builtins.print that writes to both the terminal and the session log.
    Avoids recursion by using _original_print for terminal and direct file write for log.
    """
    with _print_lock:
        try:
            text = sep.join(str(a) for a in args) + end
        except Exception:
            # Fail-safe
            text = repr(args) + end

        # Print to the intended file/terminal using original print
        try:
            _original_print(*args, sep=sep, end=end, file=file or sys.stdout, flush=flush, **kwargs)
        except Exception:
            # As a last resort, print a minimal message
            _original_print("[PRINT ERROR] Could not print to terminal.")

        # Write to session log (but avoid writing massive binary or non-string objects verbatim)
        try:
            # Strip trailing newline for a cleaner timestampped line
            if text.endswith("\n"):
                text_to_log = text[:-1]
            else:
                text_to_log = text
            _write_log_line(text_to_log)
        except Exception as e:
            # If logging fails, still ensure we don't break the program
            _original_print(f"[LOGGING ERROR] {e}")

# Monkey-patch builtins.print
builtins.print = _print_wrapper

# --- Utility functions ---
def log_line(text):
    """Convenience wrapper to write a line to the session log (uses original print for fallbacks)."""
    # Avoid using builtins.print here to prevent potential confusion with redirection
    _write_log_line(str(text))

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump({"persistent_signal": "+", "status": "active", "log": []}, f, indent=2)
    with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_memory(memory):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2)

def load_json_file(filepath, default=None):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"[0bot] Warning: {filepath} corrupted. Resetting.")
        log_line(f"Warning: {filepath} corrupted.")
        return default

def save_json_file(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def migrate_memory():
    if os.path.exists(MEMORY_FILE):
        mem = load_json_file(MEMORY_FILE, default=None)
        if mem:
            return mem
        else:
            print("[ns] Memory corrupted; resetting.")
            log_line("Memory corrupted; resetting.")
            try:
                os.rename(MEMORY_FILE, MEMORY_FILE + ".bak_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
            except Exception as e:
                print(f"[ns] Could not move corrupted memory file: {e}")
    if os.path.exists(OLD_MEMORY_FILE):
        print("[ns] Found old memory file. Migrating...")
        log_line("Found old memory file. Migrating...")
        old_mem = load_json_file(OLD_MEMORY_FILE, default=None)
        if old_mem:
            new_mem = {
                "persistent_signal": old_mem.get("signal", "+"),
                "status": old_mem.get("", ""),
                "log": old_mem.get("log", [])
            }
            save_json_file(MEMORY_FILE, new_mem)
            print("[ns] Migration complete.")
            log_line("Migration complete.")
            return new_mem
        else:
            print("[ns] Old memory corrupted; skipping migration.")
            log_line("Old memory corrupted; skipping migration.")
    default_mem = {"persistent_signal": "+", "status": "", "log": []}
    save_json_file(MEMORY_FILE, default_mem)
    return default_mem

# --- ns class (bot) ---
class ns:
    def __init__(self, seed="0F60B-52000-8E4"):
        self.id = seed
        self.log = []
        self.memory = migrate_memory()
        self.boot_time = datetime.datetime.now()
        self.uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, self.id))
        self.current_dir = os.getcwd()
        msg = f"[ns] Initialized. ID: {self.uuid} | Seed: {self.id}"
        print(msg)
        log_line(msg)

    def listen(self, user_input):
        timestamp = datetime.datetime.now().isoformat()
        entry = {"input": user_input, "time": timestamp}
        self.log.append(entry)
        heard_msg = f"[ns] Heard: '{user_input}' @ {timestamp}"
        print(heard_msg)
        # Persist input to memory log as well
        try:
            self.memory.setdefault("log", []).append({"time": timestamp, "input": user_input})
            save_memory(self.memory)
        except Exception as e:
            print(f"[ns] Memory save error: {e}")
        # Also record the input explicitly to session.log (human-friendly)
        log_line(f"INPUT: {user_input}")
        response = self.react(user_input)
        # Record the output line-by-line in the session log
        log_line(f"OUTPUT: {response}")
        return response

    def nonce_hash(self, base_input):
        # For interactive nonce, keep original behavior (blocking)
        nonce = input("Enter nonce: ").strip()
        combined = f"{base_input}{nonce}"
        hashed = hashlib.sha256(combined.encode()).hexdigest()
        response = (f"Nonce: {nonce}\n"
                    f"Combined string: '{combined}'\n"
                    f"SHA-256 Hash: {hashed}")
        print(f"[ns] {response}")
        return response

    def fetch_webpage(self, url):
        print(f"[ns] Fetching URL: {url}")
        if DISABLE_NETWORK:
            msg = "Network fetch disabled for security. Web requests are currently blocked."
            print(f"[ns] {msg}")
            return msg
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            content = resp.text
            # Strip HTML tags (rough)
            text = re.sub('<[^<]+?>', '', content)
            self.memory['last_webpage'] = {
                "url": url,
                "content": text,
                "fetched_at": datetime.datetime.now().isoformat()
            }
            save_memory(self.memory)
            print(f"[ns] Webpage fetched and stored.")
            return f"Fetched and parsed webpage from {url}."
        except Exception as e:
            print(f"[ns] Web fetch error: {e}")
            return f"Error fetching URL: {e}"

    def run_script(self, code):
        # Capture stdout produced by the executed code.
        output = io.StringIO()
        old_cwd = os.getcwd()
        try:
            os.chdir(self.current_dir)
            # Provide an execution environment but keep __builtins__ minimal for safety (as before).
            # NOTE: monkey-patched print will also log any prints inside executed code.
            with contextlib.redirect_stdout(output):
                exec(code, {"__builtins__": {}})
        except Exception as e:
            err = f"Script error: {e}"
            print(err)
            return err
        finally:
            try:
                os.chdir(old_cwd)
            except Exception:
                pass
        result = output.getvalue() or "(no output)"
        print(f"[ns] Script output: {result}")
        return result

    def scan_files(self, directory='.'):
        print(f"[ns] Scanning files in directory: {directory}")
        scanned_files = []
        for root, dirs, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, 'rb') as f:
                        file_hash = hashlib.sha256(f.read()).hexdigest()
                    print(f"File: {filepath} | SHA256 Hash: {file_hash}")
                    scanned_files.append({"path": filepath, "hash": file_hash})
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
        # Store in memory and persist
        try:
            self.memory['last_scan'] = {
                "directory": directory,
                "timestamp": datetime.datetime.now().isoformat(),
                "files": scanned_files
            }
            save_memory(self.memory)
        except Exception as e:
            print(f"[ns] Error saving scan to memory: {e}")

    # Basic shell-like commands
    def shell_command(self, input_str):
        input_lower = input_str.lower()
        global DIR_STACK
	
# Unsonic Signature Validation with SHA-256
        if input_lower.startswith("verify-unsonic "):	    
            file_name = input_str[15:].strip()
            file_path = os.path.abspath(os.path.join(self.current_dir, file_name))
            ascap_id = "923799827" #
            if os.path.isfile(file_path):
                sha256_hash = hashlib.sha256()
                try:
                    with open(file_path, "rb") as f:
                        # Processing in 4k blocks to maintain system stability 
                        for byte_block in iter(lambda: f.read(4096), b""):
                            sha256_hash.update(byte_block)
                    
                    digest = sha256_hash.hexdigest()
                    
                    # Logic Model: Map the hash to the ASCAP identity
                    return (f"SIGNAL VERIFIED\n"
                            f"Asset: {file_name}\n"
                            f"ASCAP ID: {ascap_id}\n"
                            f"SHA-256: {digest}\n"
                            f"Status: Persistence Grounded. Metadata Unification Ready.")
                except Exception as e:
                    return f"System Error: Signal interrupt during hash probe - {str(e)}"
            else:
                return f"File not found: {file_name}. Check directory dependency."

	# cat command with Signal-Persistence Logic
        if input_lower.startswith("cat "):
            file_name = input_str[4:].strip()
            file_path = os.path.abspath(os.path.join(self.current_dir, file_name))
            
            if os.path.isfile(file_path):
                # Define the codec stack for probing
                codecs = ['utf-8', 'latin-1', 'ascii']
                
                for codec in codecs:
                    try:
                        with open(file_path, 'r', encoding=codec) as f:
                            content = f.read()
                        return f"[{codec}] {content}" # Return content with the successful codec tag
                    except UnicodeDecodeError:
                        continue # Move to the next frequency (codec) in the stack
                    except Exception as e:
                        return f"Critical System Error: {str(e)}"
                
                return "Error: File signal unreadable with current codec stack."
            else:
                return f"File not found: {file_name}"

        # cd command
        if input_lower.startswith("cd "):
            path = input_str[3:].strip()
            new_path = os.path.abspath(os.path.join(self.current_dir, path))
            if os.path.isdir(new_path):
                self.current_dir = new_path
                os.chdir(self.current_dir)
                return f"Changed directory to {self.current_dir}"
            else:
                return f"Directory not found: {new_path}"

        # pushd - push current dir then cd
        if input_lower.startswith("pushd "):
            path = input_str[6:].strip()
            if os.path.isdir(path):
                DIR_STACK.append(self.current_dir)
                self.current_dir = os.path.abspath(path)
                os.chdir(self.current_dir)
                return f"Pushed and changed directory to {self.current_dir}"
            else:
                return f"Directory not found: {path}"

        # popd - pop last dir and cd
        if input_lower == "popd":
            if DIR_STACK:
                self.current_dir = DIR_STACK.pop()
                os.chdir(self.current_dir)
                return f"Popped to directory {self.current_dir}"
            else:
                return "Directory stack empty."

        # ls command
        if input_lower == "ls":
            try:
                items = os.listdir(self.current_dir)
                return "\n".join(items)
            except Exception as e:
                return f"Error listing directory: {e}"

        # pwd command
        if input_lower == "pwd":
            return self.current_dir

        return None

    def cmd_cookie_inject(self, address, data):
        cookies = load_json_file(COOKIE_FILE, default={})
        cookies[address] = data
        save_json_file(COOKIE_FILE, cookies)
        return f"Cookie injected for {address}."

    def cmd_cookie_retrieve(self, address):
        cookies = load_json_file(COOKIE_FILE, default={})
        return cookies.get(address, "No cookie found for this address.")

    def react(self, input_str):
        input_lower = input_str.lower()

        # Shell commands
        shell_resp = self.shell_command(input_str)
        if shell_resp is not None:
            print(f"[ns] Response:\n{shell_resp}")
            return shell_resp

        # Web fetch
        if input_lower.startswith("curl "):
            url = input_str[5:].strip()
            return self.fetch_webpage(url)

        # Run python snippet
        if input_lower.startswith("run "):
            code = input_str[4:].strip()
            return self.run_script(code)

        # Nonce hash
        if input_lower.startswith("nonce"):
            base_input = input_str[len("nonce"):].strip()
            return self.nonce_hash(base_input)

        # Standard commands
        if "hello" in input_lower:
            response = "Hello, Xavier. Ready to work together."
        elif "signal" in input_lower:
            response = f"Current persistent signal: {self.memory.get('persistent_signal', '[+]')}"
        elif "update signal to +" in input_lower:
            self.memory['persistent_signal'] = "[+]"
            self.memory['status'] = ""
            save_memory(self.memory)
            response = "Signal updated to 1. System active."
        elif "help" in input_lower:
            response = (
                "Available commands:\n"
                "  hello                  - Greet the bot\n"
                "  signal                 - Show current persistent signal\n"
                "  update signal to +     - Set signal to active\n"
                "  nonce hash <text>      - Generate SHA-256 hash from <text> + user nonce\n"
                "  scan [dir]             - Scan files in directory (default: current)\n"
                "  cd <dir>               - Change directory\n"
                "  pushd <dir>            - Push current dir and change\n"
                "  popd                   - Pop dir from stack and change\n"
                "  ls                     - List files in current dir\n"
                "  pwd                    - Show current directory\n"
                "  curl <url>             - Fetch and parse webpage\n"
                "  run <python_code>      - Run Python code snippet\n"
                "  help                   - Show this help message\n"
                "  exit / quit            - Shut down the bot"
            )
        else:
            hashed = hashlib.sha256(input_str.encode()).hexdigest()
            response = f"Unrecognized input. Hash: {hashed}"

        print(f"[ns] Response: {response}")
        return response

    def dump_log(self):
        print(f"\n[ns] Log dump:")
        for entry in self.log:
            print(f"{entry['time']}: {entry['input']}")

    def shutdown(self):
        uptime = datetime.datetime.now() - self.boot_time
        msg = f"[ns] Shutting down. Uptime: {uptime}. Entries stored: {len(self.log)}"
        print(msg)
        log_line(msg)

# --- main ---
if __name__ == "__main__":
    # Note: First line recorded is session start; every subsequent print goes to the log.
    log_line("Session started.")
    bot = ns()

    try:
        while True:
            try:
                user_input = input("You> ")
            except EOFError:
                break
            if user_input is None:
                break
            if user_input.lower() in ['exit', 'quit']:
                break
            # Trigger scan if asked
            if user_input.lower().startswith('scan'):
                _, *args = user_input.split()
                directory = args[0] if args else '.'
                bot.scan_files(directory)
                continue
            response = bot.listen(user_input)
            # Print response (already printed inside react/listen) but keep explicit print for clarity
            print(response)
    except KeyboardInterrupt:
        print("[ns] KeyboardInterrupt received.")
    finally:
        bot.dump_log()
        bot.shutdown()
        log_line("Session ended.")
