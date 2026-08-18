# Verifica la integridad de nuclei: compara el zip descargado con el
# checksum oficial publicado por ProjectDiscovery en GitHub.
$ErrorActionPreference = 'Stop'
$rel = Invoke-RestMethod https://api.github.com/repos/projectdiscovery/nuclei/releases/latest
Write-Host "Release: $($rel.tag_name)"
$zipAsset = $rel.assets | Where-Object { $_.name -match 'windows_amd64.zip$' } | Select-Object -First 1
$chkAsset = $rel.assets | Where-Object { $_.name -match 'checksums' } | Select-Object -First 1
Write-Host "Asset: $($zipAsset.name)  |  Checksums: $($chkAsset.name)"

$zip = "$env:TEMP\nuclei-verify.zip"
Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zip
$local = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()

$chk = Invoke-RestMethod -Uri $chkAsset.browser_download_url
$official = ($chk -split "`n" | Where-Object { $_ -match $zipAsset.name } | Select-Object -First 1) -split '\s+' | Select-Object -First 1

Write-Host "SHA256 local:    $local"
Write-Host "SHA256 oficial:  $($official.ToLower())"
if ($local -eq $official.ToLower()) {
    Write-Host "RESULTADO: COINCIDE — el binario es el oficial de ProjectDiscovery"
} else {
    Write-Host "RESULTADO: NO COINCIDE — algo va mal, no instalar"
}
Remove-Item $zip -ErrorAction SilentlyContinue
