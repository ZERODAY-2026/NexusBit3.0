# Privacy proof (Windows): sample every second the TCP connections owned by the LexLocal
# Python/Streamlit process(es) and Ollama, and flag anything that is not loopback.
#   powershell -ExecutionPolicy Bypass -File scripts\monitor_connections.ps1 [-Seconds 120] [-Out logs\connections.csv]
param([int]$Seconds = 120, [string]$Out = "logs\connections.csv")
$ErrorActionPreference = "SilentlyContinue"
New-Item -ItemType Directory -Force (Split-Path $Out) | Out-Null
"time,process,pid,local,remote,state,loopback" | Set-Content $Out -Encoding utf8
$nonLoop = 0; $total = 0
for ($i = 0; $i -lt $Seconds; $i++) {
    $procs = Get-Process | Where-Object { $_.ProcessName -match '^(python|pythonw|streamlit|ollama|ollama_llama_server|llama-server)$' }
    $ids = $procs.Id
    $conns = Get-NetTCPConnection | Where-Object { $ids -contains $_.OwningProcess -and $_.State -ne 'Listen' }
    foreach ($c in $conns) {
        $name = ($procs | Where-Object Id -eq $c.OwningProcess).ProcessName
        $loop = ($c.RemoteAddress -match '^(127\.|::1$|0\.0\.0\.0$|::$)')
        $total++
        if (-not $loop) { $nonLoop++; Write-Host "NON-LOOPBACK: $name $($c.RemoteAddress):$($c.RemotePort)" -ForegroundColor Red }
        "$(Get-Date -Format HH:mm:ss),$name,$($c.OwningProcess),$($c.LocalAddress):$($c.LocalPort),$($c.RemoteAddress):$($c.RemotePort),$($c.State),$loop" | Add-Content $Out
    }
    Write-Host -NoNewline "`r[$($i+1)/$Seconds] connections seen: $total  non-loopback: $nonLoop   "
    Start-Sleep -Seconds 1
}
Write-Host ""
if ($nonLoop -eq 0) { Write-Host "RESULT: only loopback connections observed ($total samples). Log: $Out" -ForegroundColor Green }
else { Write-Host "RESULT: $nonLoop non-loopback connection samples observed! See $Out" -ForegroundColor Red; exit 1 }
