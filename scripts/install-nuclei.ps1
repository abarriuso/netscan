# Instala nuclei (no disponible en winget) en %LOCALAPPDATA%\NetScan\bin
$ErrorActionPreference = 'Stop'
$d = "$env:LOCALAPPDATA\NetScan\bin"
New-Item -ItemType Directory -Force -Path $d | Out-Null
$rel = Invoke-RestMethod https://api.github.com/repos/projectdiscovery/nuclei/releases/latest
$asset = $rel.assets | Where-Object { $_.name -match 'windows_amd64.zip$' } | Select-Object -First 1
Write-Host "Descargando $($asset.name)"
$zip = "$env:TEMP\nuclei.zip"
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip
Expand-Archive -Force $zip $d
Remove-Item $zip
$p = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($p -notlike "*$d*") { [Environment]::SetEnvironmentVariable('Path', "$p;$d", 'User') }
Get-ChildItem $d -Filter nuclei* | Select-Object -First 3 Name
