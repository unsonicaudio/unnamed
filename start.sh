param(
  [string]$LlamaServer = ".\llama-server.exe",
  [string]$Model = ".\models\qwen3-4b\Qwen3-4B-Q4_K_M.gguf"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path $LlamaServer)) { throw "llama-server not found: $LlamaServer" }
if (-not (Test-Path $Model)) { throw "Model not found: $Model" }
& $LlamaServer -m $Model --host 127.0.0.1 --port 8090 -c 8192
