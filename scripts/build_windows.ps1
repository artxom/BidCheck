param(
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"

$Root = (Get-Location).Path
$FrontendDir = Join-Path $Root "frontend"
$FrontendIndex = Join-Path $FrontendDir "dist\index.html"
$DistDir = Join-Path $Root "dist\BidGuard"
$ReleaseDir = Join-Path $Root "release"
$ZipPath = Join-Path $ReleaseDir "BidGuard-Windows-x64.zip"

if (-not $SkipFrontendBuild) {
    Write-Host "==> Building Frontend SPA..."
    Push-Location $FrontendDir
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path $FrontendIndex)) {
    throw "Frontend production bundle missing at $FrontendIndex"
}

Write-Host "==> Generating Windows Icon..."
python (Join-Path $Root "packaging\generate_icon.py") (Join-Path $Root "build\bidguard.ico")
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

Write-Host "==> Cleaning Previous Build & Release Outputs..."
if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
if (Test-Path "$ZipPath.sha256") { Remove-Item -Force "$ZipPath.sha256" }
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

Write-Host "==> Packaging BidGuard.exe with PyInstaller (--onedir)..."
python -m PyInstaller --noconfirm --clean (Join-Path $Root "packaging\bidguard.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$ExePath = Join-Path $DistDir "BidGuard.exe"
if (-not (Test-Path $ExePath)) {
    throw "Expected executable not found at $ExePath"
}

Write-Host "==> Smoke-testing Standalone BidGuard.exe (--self-test)..."
$TempData = Join-Path $Root "build\selftest_data"
$SelfTestJson = Join-Path $Root "build\selftest.json"
if (Test-Path $TempData) { Remove-Item -Recurse -Force $TempData }
if (Test-Path $SelfTestJson) { Remove-Item -Force $SelfTestJson }
New-Item -ItemType Directory -Force -Path $TempData | Out-Null

$env:BIDGUARD_DATA_DIR = $TempData
try {
    $proc = Start-Process -FilePath $ExePath -ArgumentList @("--self-test", "--self-test-out", $SelfTestJson) -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "BidGuard.exe --self-test exited with code $($proc.ExitCode)"
    }
}
finally {
    Remove-Item Env:BIDGUARD_DATA_DIR -ErrorAction SilentlyContinue
}

if (-not (Test-Path $SelfTestJson)) {
    throw "Self-test JSON report missing at $SelfTestJson"
}
$SelfTestResult = Get-Content $SelfTestJson -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $SelfTestResult.ok) {
    throw "BidGuard.exe self-test reported failure: $($SelfTestResult.error)"
}

$BundledData = Join-Path $DistDir "data"
if (Test-Path $BundledData) {
    Remove-Item -Recurse -Force $BundledData
}

Write-Host "==> Writing Quick-Start Guide (使用说明.txt)..."
$GuideLines = @(
    "标书智检 (BidGuard) Windows 免安装独立版 使用说明",
    "================================================",
    "1. 请先将整个压缩包完整解压至任意本地目录（请勿直接在压缩包预览窗口双击运行）。",
    "2. 双击 BidGuard.exe 启动工作台，系统会自动打开独立应用窗口或默认浏览器。",
    "3. 首次使用请在工作台按 Ctrl + , 打开设置面板，填入大模型供应商 API Key 并绑定四角色模型。",
    "4. 项目数据与本地配置保存在同级 data\\ 文件夹中；后续版本升级时保留原 data\\ 目录即可无缝继承历史项目与配置。"
)
$GuideText = ($GuideLines -join "`r`n") + "`r`n"
[System.IO.File]::WriteAllText((Join-Path $DistDir "使用说明.txt"), $GuideText, [System.Text.UTF8Encoding]::new($true))

Write-Host "==> Creating Release Zip Archive: $ZipPath"
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $DistDir,
    $ZipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true
)

$HashHex = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText("$ZipPath.sha256", "$HashHex  BidGuard-Windows-x64.zip`n", [System.Text.UTF8Encoding]::new($false))

Write-Host "==> Windows standalone package built successfully: $ZipPath"
