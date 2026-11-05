param([int]$Port = 8000, [switch]$UseRealModel)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$pythonPath = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '无法创建 Python 环境' }
}
& $pythonPath -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
$modeTag = if ($UseRealModel) { 'api' } else { 'mock' }
$promptTag = & $pythonPath -c "from app.agent import PROMPT_VERSION; print(PROMPT_VERSION)"
if ($LASTEXITCODE -ne 0 -or $promptTag -notmatch '^[a-zA-Z0-9_-]+$') { throw '无法确定处理版本' }
$env:DATABASE_URL = "sqlite:///./data/$modeTag-$promptTag.sqlite3"
$env:STORAGE_DIR = './data/uploads'
$env:LLM_MODE = if ($UseRealModel) { 'api' } else { 'mock' }
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path data | Out-Null
& $pythonPath -m app.db
if ($LASTEXITCODE -ne 0) { throw '初始化失败' }
$worker = Start-Process -FilePath $pythonPath -ArgumentList '-m','scripts.demo_worker' -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data/demo-worker.log' -RedirectStandardError 'data/demo-worker-error.log'
try {
    Write-Host "页面：http://127.0.0.1:$Port（模式 $env:LLM_MODE；Ctrl+C 退出）"
    & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port
} finally {
    if (-not $worker.HasExited) { $worker.Kill() }
}
