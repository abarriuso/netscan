# Instala nuclei (no disponible en winget) en %LOCALAPPDATA%\NetScan\bin
# verificando el SHA256 contra el checksums.txt oficial de ProjectDiscovery.
# Si el hash no coincide, aborta SIN instalar nada.
$ErrorActionPreference = 'Stop'
$d = "$env:LOCALAPPDATA\NetScan\bin"
New-Item -ItemType Directory -Force -Path $d | Out-Null

$rel = Invoke-RestMethod https://api.github.com/repos/projectdiscovery/nuclei/releases/latest
$zipAsset = $rel.assets | Where-Object { $_.name -match 'windows_amd64.zip$' } | Select-Object -First 1
$chkAsset = $rel.assets | Where-Object { $_.name -match 'checksums' } | Select-Object -First 1
if (-not $zipAsset -or -not $chkAsset) { Write-Error "No se encontraron los assets de la release"; exit 1 }

Write-Host "Descargando $($zipAsset.name) ($($rel.tag_name))"
$zip = "$env:TEMP\nuclei.zip"
Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zip

# Verificación de integridad ANTES de extraer
$local = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
$chk = Invoke-RestMethod -Uri $chkAsset.browser_download_url
$official = (($chk -split "`n" | Where-Object { $_ -match $zipAsset.name } | Select-Object -First 1) -split '\s+')[0].ToLower()
if (-not $official -or $local -ne $official) {
    Remove-Item $zip -ErrorAction SilentlyContinue
    Write-Error "SHA256 NO COINCIDE (local: $local, oficial: $official). Abortando."
    exit 1
}
Write-Host "SHA256 verificado: $local"

Expand-Archive -Force $zip $d
Remove-Item $zip
$p = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($p -notlike "*$d*") {
    [Environment]::SetEnvironmentVariable('Path', "$p;$d", 'User')

    # SetEnvironmentVariable solo escribe en el registro: Explorer (y por
    # tanto cualquier cmd/acceso directo nuevo lanzado desde el escritorio)
    # sigue usando su bloque de entorno en memoria hasta que recibe este
    # broadcast, o hasta cerrar sesion. Sin esto, nuclei queda instalado
    # pero invisible para NetScan en la siguiente ejecucion normal.
    $sig = '[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
            public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);'
    $type = Add-Type -MemberDefinition $sig -Name Win32SendMessageTimeout -Namespace Win32Broadcast -PassThru
    $HWND_BROADCAST = [IntPtr]0xffff
    $WM_SETTINGCHANGE = 0x1a
    $SMTO_ABORTIFHUNG = 0x2
    $result = [UIntPtr]::Zero
    $type::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [UIntPtr]::Zero, 'Environment', $SMTO_ABORTIFHUNG, 5000, [ref]$result) | Out-Null
}
Get-ChildItem $d -Filter nuclei* | Select-Object -First 3 Name
