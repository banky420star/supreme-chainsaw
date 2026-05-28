# Supreme Chainsaw - Create Desktop Launchers with Distinct Icons
# Run this once (or anytime after updates) to (re)create the three desktop shortcuts.

param(
    [switch]$Force
)

$ErrorActionPreference = "Continue"
$repoRoot = "C:\supreme-chainsaw"
Set-Location $repoRoot

trap {
    Write-Host ""
    Write-Host "[ERROR] Desktop shortcut creation had a problem: $_" -ForegroundColor Red
    Write-Host "You can still run the launchers manually from DesktopLaunchers\ folder." -ForegroundColor Yellow
    Write-Host ""
    pause
}

$desktop = [Environment]::GetFolderPath("Desktop")
$assetsDir = Join-Path $repoRoot "assets"
$launchersDir = Join-Path $repoRoot "DesktopLaunchers"
$venvPython = Join-Path $repoRoot ".venv312\Scripts\python.exe"

# Ensure assets dir exists
if (-not (Test-Path $assetsDir)) { New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null }

Write-Host "=== Creating Supreme Chainsaw Desktop Launchers ===" -ForegroundColor Cyan

# ============================================================
# Generate 3 distinct simple icons using Pillow (if available)
# ============================================================
$iconMini   = Join-Path $assetsDir "icon_mini_tui.ico"
$iconFull   = Join-Path $assetsDir "icon_full_stack.ico"
$iconReact  = Join-Path $assetsDir "icon_react_ui.ico"

$iconMiniPath = $iconMini -replace '\\', '/'
$iconFullPath = $iconFull -replace '\\', '/'
$iconReactPath = $iconReact -replace '\\', '/'

$iconScript = @"
from PIL import Image, ImageDraw, ImageFont
import sys

def create_icon(output_path, color, letter):
    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([20, 20, 236, 236], radius=40, fill=color)
    try:
        font = ImageFont.truetype("arial.ttf", 140)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), letter, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (256 - w) // 2
    y = (256 - h) // 2 - 10
    draw.text((x, y), letter, fill="white", font=font)
    img.save(output_path, format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
    print(f"Created: {output_path}")

# Mini TUI - Purple
create_icon(r"$iconMiniPath", (139, 92, 246), "M")

# Full Stack - Green
create_icon(r"$iconFullPath", (34, 197, 94), "F")

# React UI - Blue
create_icon(r"$iconReactPath", (59, 130, 246), "R")

print("All icons generated successfully.")
"@

$hasPillow = $false
if (Test-Path $venvPython) {
    try {
        & $venvPython -c "from PIL import Image; print('Pillow OK')" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $hasPillow = $true }
    } catch {}
}

if ($hasPillow) {
    Write-Host "Generating distinct colored icons using Pillow..." -ForegroundColor Green
    try {
        $tmpPy = Join-Path $env:TEMP "gen_icons_$(Get-Random).py"
        $iconScript | Out-File -FilePath $tmpPy -Encoding UTF8 -Force
        & $venvPython $tmpPy 2>&1
        Remove-Item $tmpPy -ErrorAction SilentlyContinue
    } catch {
        Write-Host "Pillow icon generation failed ($_) - falling back to system icons for shortcuts." -ForegroundColor Yellow
        $iconMini  = "%SystemRoot%\System32\imageres.dll,109"
        $iconFull  = "%SystemRoot%\System32\imageres.dll,101"
        $iconReact = "%SystemRoot%\System32\imageres.dll,104"
    }
} else {
    Write-Host "Pillow not available in .venv312. Using reliable system icons for the desktop shortcuts." -ForegroundColor Yellow
    $iconMini  = "%SystemRoot%\System32\imageres.dll,109"
    $iconFull  = "%SystemRoot%\System32\imageres.dll,101"
    $iconReact = "%SystemRoot%\System32\imageres.dll,104"
}

# ============================================================
# Create the three desktop shortcuts
# ============================================================

function New-DesktopShortcut {
    param(
        [string]$Name,
        [string]$TargetPs1,
        [string]$IconLocation,
        [string]$Description
    )
    
    $shortcutPath = Join-Path $desktop "$Name.lnk"
    
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$TargetPs1`""
    $shortcut.WorkingDirectory = $repoRoot
    $shortcut.Description = $Description
    $shortcut.WindowStyle = 1
    $shortcut.IconLocation = $IconLocation
    $shortcut.Save()
    
    Write-Host "Created desktop shortcut: $shortcutPath" -ForegroundColor Green
}

# 1. Mini TUI
New-DesktopShortcut `
    -Name "Supreme Chainsaw - Mini TUI" `
    -TargetPs1 (Join-Path $launchersDir "Mini_TUI_Launcher.ps1") `
    -IconLocation $iconMini `
    -Description "Compact live view of the full autonomous trading pipeline (Decision PPO + Patterns + Timing + Execution)"

# 2. Full Stack
New-DesktopShortcut `
    -Name "Supreme Chainsaw - Full Stack" `
    -TargetPs1 (Join-Path $launchersDir "Full_Stack_Launcher.ps1") `
    -IconLocation $iconFull `
    -Description "Complete production stack: Backend API + React UI + Rich TUI + Supervisor"

# 3. React UI
New-DesktopShortcut `
    -Name "Supreme Chainsaw - React UI" `
    -TargetPs1 (Join-Path $launchersDir "React_UI_Launcher.ps1") `
    -IconLocation $iconReact `
    -Description "Production React Dashboard (frontend only) - connects to api_server on port 5050"

Write-Host ""
Write-Host "=== All three desktop launchers created successfully ===" -ForegroundColor Cyan
Write-Host "You should now see them on your Desktop:" -ForegroundColor White
Write-Host "  • Supreme Chainsaw - Mini TUI" -ForegroundColor Magenta
Write-Host "  • Supreme Chainsaw - Full Stack" -ForegroundColor Green
Write-Host "  • Supreme Chainsaw - React UI" -ForegroundColor Blue
Write-Host ""
Write-Host "Icons are distinct (purple M, green F, blue R)." -ForegroundColor DarkGray
Write-Host "Right-click → Properties to change icons later if desired." -ForegroundColor DarkGray