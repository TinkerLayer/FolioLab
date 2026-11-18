# Folio Lab setup: installs portable Node.js and portable MiKTeX into .\tools (no admin rights,
# nothing outside this folder) and the Python packages the analysis modules need.
# Safe to run again; finished steps are skipped.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root  = $PSScriptRoot
$Tools = Join-Path $Root 'tools'
New-Item -ItemType Directory -Force $Tools | Out-Null

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# ------------------------------------------------------------------ Node.js
$NodeDir = Join-Path $Tools 'node'
if (-not (Test-Path "$NodeDir\node.exe")) {
    Step 'Downloading portable Node.js (LTS)'
    $idx = Invoke-RestMethod 'https://nodejs.org/dist/index.json'
    $v = ($idx | Where-Object { $_.lts -and ($_.files -contains 'win-x64-zip') } | Select-Object -First 1).version
    $zip = Join-Path $Tools 'node.zip'
    Invoke-WebRequest "https://nodejs.org/dist/$v/node-$v-win-x64.zip" -OutFile $zip
    tar -xf $zip -C $Tools
    Rename-Item (Join-Path $Tools "node-$v-win-x64") 'node'
    Remove-Item $zip
    Write-Host "Node.js $v installed."
} else { Write-Host 'Node.js already installed.' }

# ------------------------------------------------------------------ npm packages (editor + PDF viewer)
if (-not (Test-Path (Join-Path $Root 'node_modules\monaco-editor\min\vs\loader.js'))) {
    Step 'Installing editor and PDF viewer libraries'
    $env:PATH = "$NodeDir;$env:PATH"
    Push-Location $Root
    & "$NodeDir\npm.cmd" install --no-audit --no-fund
    Pop-Location
}

# ------------------------------------------------------------------ MiKTeX (portable)
$MiKTeXDir = Join-Path $Tools 'miktex'
$Bin = Join-Path $MiKTeXDir 'texmfs\install\miktex\bin\x64'
if (-not (Test-Path "$Bin\pdflatex.exe")) {
    Step 'Downloading MiKTeX setup utility'
    $page = Invoke-WebRequest 'https://miktex.org/download' -UseBasicParsing
    $href = ($page.Links | Where-Object { $_.href -match 'miktexsetup-.*-x64\.zip' } | Select-Object -First 1).href
    if (-not $href) { throw 'Could not find the MiKTeX setup download on miktex.org/download' }
    $href = $href -replace '&#x2B;', '+'
    if ($href.StartsWith('/')) { $href = "https://miktex.org$href" }
    $setupZip = Join-Path $Tools 'miktexsetup.zip'
    Invoke-WebRequest $href -OutFile $setupZip
    New-Item -ItemType Directory -Force (Join-Path $Tools 'miktexsetup') | Out-Null
    tar -xf $setupZip -C (Join-Path $Tools 'miktexsetup')
    $setup = Join-Path $Tools 'miktexsetup\miktexsetup_standalone.exe'
    $repo = Join-Path $Tools 'miktex-repo'

    Step 'Downloading the MiKTeX basic package set (a few hundred MB, takes a while)'
    & $setup --verbose "--local-package-repository=$repo" --package-set=basic download
    if ($LASTEXITCODE -ne 0) { throw 'MiKTeX download failed' }

    Step 'Installing portable MiKTeX'
    & $setup --verbose "--local-package-repository=$repo" --package-set=basic "--portable=$MiKTeXDir" install
    if ($LASTEXITCODE -ne 0) { throw 'MiKTeX install failed' }

    Remove-Item -Recurse -Force $repo, $setupZip, (Join-Path $Tools 'miktexsetup') -ErrorAction SilentlyContinue
} else { Write-Host 'MiKTeX already installed.' }

Step 'Configuring MiKTeX to install missing packages automatically'
& "$Bin\initexmf.exe" --set-config-value=[MPM]AutoInstall=1 | Out-Null
$mirror = & "$Bin\mpm.exe" --pick-repository-url 2>$null | Select-Object -Last 1
if ($mirror) { & "$Bin\mpm.exe" "--set-repository=$mirror" | Out-Null; Write-Host "Package mirror: $mirror" }
& "$Bin\miktex.exe" packages update-package-database 2>$null | Out-Null

# ------------------------------------------------------------------ Python for analysis modules
# Modules under .\modules run as small local Python apps. Python itself is not downloaded here;
# the hub looks for it in the same order (LAB_PYTHON, per-user install, py launcher, PATH).
Step 'Checking Python for the analysis modules'
$Py = $null
$cands = @()
if ($env:LAB_PYTHON) { $cands += ,@($env:LAB_PYTHON) }
$pyBase = Join-Path $env:LOCALAPPDATA 'Programs\Python'
if (Test-Path $pyBase) {
    Get-ChildItem $pyBase -Directory | Where-Object Name -match '^Python3\d+$' |
        Sort-Object { [int]($_.Name.Substring(7)) } -Descending |
        ForEach-Object { $cands += ,@((Join-Path $_.FullName 'python.exe')) }
}
$cands += ,@('py', '-3'); $cands += ,@('python')
foreach ($c in $cands) {
    try {
        $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
        $v = & $exe @pre -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>$null
        if ($LASTEXITCODE -eq 0 -and [int]$v -ge 310) { $Py = $c; break }
    } catch { }
}
if (-not $Py) {
    Write-Host 'Python 3.10 or newer was not found. The report editor works without it, but analysis modules will not start.' -ForegroundColor Yellow
    Write-Host 'Install it from https://www.python.org/downloads/ (or: winget install Python.Python.3.12), then run setup.ps1 again.' -ForegroundColor Yellow
} else {
    $exe = $Py[0]; $pre = @($Py | Select-Object -Skip 1)
    Write-Host "Python: $(& $exe @pre -c 'import sys; print(sys.executable)')"
    $reqs = @()
    Get-ChildItem (Join-Path $Root 'modules') -Directory | ForEach-Object {
        $rf = Join-Path $_.FullName 'requirements.txt'
        if (Test-Path $rf) { $reqs += Get-Content $rf | Where-Object { $_ -and -not $_.StartsWith('#') } }
    }
    $reqs = $reqs | Sort-Object -Unique
    if ($reqs) {
        $mods = ($reqs | ForEach-Object { ($_ -split '[<>=!~ ]')[0] }) -join ','
        & $exe @pre -c "import importlib.util,sys; m=[x for x in '$mods'.split(',') if not importlib.util.find_spec(x)]; sys.exit(1 if m else 0)" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Step "Installing Python packages for the modules: $($reqs -join ', ')"
            & $exe @pre -m pip install --user --disable-pip-version-check @reqs
            if ($LASTEXITCODE -ne 0) { Write-Host 'pip install failed; the affected modules will not start.' -ForegroundColor Yellow }
        } else { Write-Host 'Module packages already installed.' }
    }
}

# ------------------------------------------------------------------ sample images for templates
if (-not (Test-Path (Join-Path $Root 'server\templates\article\files\images\landscape.png'))) {
    & "$NodeDir\node.exe" (Join-Path $Root 'scripts\make-sample-images.js') | Out-Null
}

Write-Host "`nSetup complete. Double-click 'Start Folio Lab.bat' to launch it." -ForegroundColor Green
