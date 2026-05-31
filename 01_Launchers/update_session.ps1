# update_session.ps1
# Updates session.json with demo MT5 credentials
# Login and server are passed as arguments or use the values below

param(
    [string]$Login = "435656990",
    [string]$Server = "Exness-MT5Trial9"
)

$sessionPath = "C:\Users\Administrator\Desktop\SupremeChainsaw_Clean\06_Data_Templates\runtime\session.json"

if (-not (Test-Path $sessionPath)) {
    Write-Error "session.json not found at: $sessionPath"
    exit 1
}

try {
    $content = Get-Content $sessionPath -Raw | ConvertFrom-Json

    # Update login and server
    $content.login = $Login
    $content.server = $Server

    # Write back with pretty formatting
    $content | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding UTF8

    Write-Host "session.json updated successfully:" -ForegroundColor Green
    Write-Host "  Login : $Login"
    Write-Host "  Server: $Server"
    Write-Host "  Path  : $sessionPath"
} catch {
    Write-Error "Failed to update session.json: $_"
    exit 1
}