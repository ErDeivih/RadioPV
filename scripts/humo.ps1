# Humo de arranque de la API de RadioPV. Uso:  .\scripts\humo.ps1 [BASE_URL]
param([string]$Base = "http://127.0.0.1:8000")

$ErrorActionPreference = "Stop"

Write-Host "== /health =="
$h = Invoke-RestMethod "$Base/health"
Write-Host ("  status={0} tracks={1} artists={2} similar={3} users={4}" -f $h.status, $h.tracks, $h.artists, $h.similar, $h.users)
if ($h.status -ne "ok") { throw "health no ok" }

Write-Host "== /tracks?limit=3 =="
$t = Invoke-RestMethod "$Base/tracks?limit=3"
Write-Host "  " $t.Count "canciones"
if ($t.Count -eq 0) { Write-Warning "  /tracks vacío" }

Write-Host "== /facets =="
$f = Invoke-RestMethod "$Base/facets"
Write-Host ("  generos={0} eras={1}" -f ($f.genres | Measure-Object).Count, ($f.eras | Measure-Object).Count)

Write-Host ""
Write-Host "OK humo de arranque."
