{
  "vobj_version": "0.1",
  "object_type": "language_model",
  "id": "model:qwen3-4b",
  "name": "TRON Local Mind",
  "provider": "Qwen",
  "runtime": {
    "engine": "llama.cpp",
    "protocol": "openai-compatible",
    "endpoint": "http://127.0.0.1:8090/v1",
    "model_name": "qwen3-4b",
    "model_format": "gguf"
  },
  "weights": {
    "file": "Qwen3-4B-Q4_K_M.gguf",
    "sha256": "REPLACE_AFTER_DOWNLOADING_AND_VERIFYING_THE_MODEL"
  },
  "capabilities": ["chat", "summarize", "command_proposal", "planning"],
  "permissions": {
    "host_filesystem": false,
    "network": false,
    "shell_execution": false,
    "protected_vault": false,
    "vfs_read": ["/mind/public", "/help"],
    "vfs_write": ["/mind/sessions"]
  },
  "limits": {
    "context_tokens": 8192,
    "max_output_tokens": 512,
    "timeout_seconds": 90
  }
}
