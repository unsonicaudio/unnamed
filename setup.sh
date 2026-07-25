# TRON Alpha 0.1

TRON Alpha is a runnable, local-first “smart computer” prototype. It combines a
browser desktop, Trone virtual phone, MindSERV-style command/chat interface,
X OUT hash-seed game, content-addressed object store, directory manifests,
named session snapshots, and a validated local-model cartridge.

It is an application prototype—not an operating system, cellular stack,
cryptocurrency, quantum-security system, or production sandbox.

## Quick start

Requirements: Python 3.10+ and a current browser.

### Windows

```powershell
.\setup.ps1
.\start.ps1
```

### macOS / Linux

```sh
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

Open `http://127.0.0.1:8765`. The server binds only to loopback by default.

No third-party Python runtime dependency is required; editable installation is
used only to make the `tron` command available.

## MindSERV commands

```text
help
status
objects
import "C:\path\to\file-or-directory"
SaveCLI demo
snapshots
LoadCLI demo
model verify
model status
chat Tell me about this system
```

`LoadCLI` restores session metadata such as the virtual working directory. It
does not overwrite host files or roll back the object store.

## Local Qwen model

The supplied VOBJ manifest is:

```text
models/qwen3-4b/model.vobj.json
```

1. Install a compatible `llama.cpp` build separately.
2. Obtain a legitimate Qwen3-4B GGUF Q4_K_M file from its official distributor.
3. Put it at `models/qwen3-4b/Qwen3-4B-Q4_K_M.gguf`.
4. Compute its SHA-256 and replace the placeholder in `model.vobj.json`.
5. Start it with `.\start-model.ps1 -LlamaServer <path-to-llama-server.exe>`.
6. Run `model verify`, then `model status` in TRON.

The package deliberately does not download multi-gigabyte model weights or
invent a digest. The daemon accepts only loopback endpoints in Alpha.

## Implemented

- Local threaded HTTP daemon and REST endpoints
- Desktop-style responsive web UI
- Trone phone launcher with Chat, Shell, Explorer, Game, System, and Dial stub
- MindSERV direct-command parser plus natural-language fallback
- OpenAI-compatible local `llama.cpp` chat client
- VOBJ model-manifest schema checks and GGUF SHA-256 verification
- SHA-256 content-addressed file objects
- Deterministic directory manifests (Merkle-style root over sorted entries)
- Named `SaveCLI` snapshots and snapshot listing/loading
- X OUT deterministic SHA-256 browser toy
- Windows and Unix setup/start scripts
- Automated tests for storage, manifests, endpoint policy, and snapshot names

## Scaffolded / intentionally not claimed

- `Dial`/TronNet: UI placeholder only; no peer protocol or vSIM network
- VFS: object and manifest skeleton, not a mounted kernel filesystem
- Model lifecycle: verification/health/chat are implemented; process sandboxing,
  hot mounting, multi-model coordination, and capability brokering are not
- Snapshots: session/catalog metadata only, not full filesystem rollback
- Natural-language actions: advice and chat only; model output never executes
- Security: local binding, path checks, payload limits, and manifest validation
  are present; signed cartridges, PQ signatures, encryption, vault isolation,
  and hostile-code containment are future work
- Learning: chat history can be snapshotted, but model weights are never modified
- CPU jitter: omitted as a security primitive; operating-system randomness should
  be used for keys. A future telemetry experiment must not be marketed as entropy
  without formal testing
- Legacy phones/browsers: responsive web design is included, but iPhone 6,
  BlackBerry, and Windows Phone compatibility is not guaranteed

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Data layout

Runtime data is created under `data/`:

```text
data/
  objects/       immutable payloads named by SHA-256
  manifests/     typed JSON descriptions
  snapshots/     named session states
  vfs/           reserved virtual namespace
```

Do not expose this Alpha daemon to the public internet.
