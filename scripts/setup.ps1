# LexLocal setup for Windows (PowerShell). Network is used ONLY here (pip, model downloads).
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "Python 3.11+ not found on PATH" }
$ver = & python -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
Write-Host "Using Python $ver"

if (-not (Test-Path .venv)) { python -m venv .venv }
$vpy = ".\.venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip

# CPU torch unless an NVIDIA GPU + CUDA is wanted (bge-small is fast on CPU; Gemma runs in Ollama)
& $vpy -m pip install torch --index-url https://download.pytorch.org/whl/cpu
& $vpy -m pip install -r requirements.txt

Write-Host "Downloading embedding model (setup-time only)..."
& $vpy scripts\download_models.py

Write-Host "Generating PDF samples / edge cases..."
& $vpy scripts\make_samples.py

Write-Host "Checking Ollama on 127.0.0.1:11434..."
try {
    $tags = Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 5
    $names = $tags.models.name
    foreach ($m in @("gemma4:e4b", "gemma4:e2b")) {
        if ($names -notcontains $m) {
            Write-Host "Pulling $m (this can take a while)..."
            Invoke-RestMethod -Method Post http://127.0.0.1:11434/api/pull -Body (@{model=$m; stream=$false} | ConvertTo-Json) -ContentType 'application/json' -TimeoutSec 7200 | Out-Null
        } else { Write-Host "  $m present" }
    }
} catch { Write-Warning "Ollama not reachable. Install from https://ollama.com and run 'ollama serve', then: ollama pull gemma4:e4b" }

if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "`nSetup complete. Run:  .\.venv\Scripts\python -m streamlit run app.py"
