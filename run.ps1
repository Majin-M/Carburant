<#
=============================================================================
Pipeline complet : ingestion -> dbt build -> export
=============================================================================
Utilisation :
    .\run.ps1                  # exécution quotidienne (année en cours)
    .\run.ps1 2025 2026        # reprise de l'historique, puis dbt et export

    Sous Linux ou macOS, avec PowerShell 7 : pwsh ./run.ps1

Chaque étape est chronométrée ; le pipeline s'arrête à la première en échec
et renvoie le code de sortie 1. Si l'environnement virtuel .venv existe et
n'est pas activé, ses programmes (python, dbt) sont utilisés quand même.
=============================================================================
#>

$ErrorActionPreference = 'Stop'
$racine = $PSScriptRoot
$annees = $args

# Utilise .venv sans exiger qu'il soit activé : Scripts sous Windows, bin ailleurs.
$venv = Join-Path $racine '.venv'
$binaires = if ($IsLinux -or $IsMacOS) { Join-Path $venv 'bin' } else { Join-Path $venv 'Scripts' }
if (-not $env:VIRTUAL_ENV -and (Test-Path $binaires)) {
    $env:PATH = $binaires + [IO.Path]::PathSeparator + $env:PATH
}
# Les accents des journaux Python restent lisibles, quel que soit l'encodage du terminal.
$env:PYTHONIOENCODING = 'utf-8'

function Invoke-Etape {
    param([string]$Nom, [scriptblock]$Commande)
    Write-Host ("=" * 60)
    Write-Host "[DÉBUT] $Nom"
    $chrono = [Diagnostics.Stopwatch]::StartNew()
    & $Commande
    $code = $LASTEXITCODE
    $duree = $chrono.Elapsed.TotalSeconds
    if ($code -ne 0) {
        Write-Host ("[ÉCHEC] {0} après {1:N1} s (code de sortie {2})" -f $Nom, $duree, $code) -ForegroundColor Red
        Write-Host ("Pipeline interrompu après {0:N1} s" -f $script:total.Elapsed.TotalSeconds) -ForegroundColor Red
        exit 1
    }
    Write-Host ("[OK]    {0} en {1:N1} s" -f $Nom, $duree) -ForegroundColor Green
}

$script:total = [Diagnostics.Stopwatch]::StartNew()

Invoke-Etape "Ingestion" { python (Join-Path $racine 'ingest.py') @annees }
Invoke-Etape "dbt build : modèles et tests" {
    Push-Location (Join-Path $racine 'dbt')
    try { dbt build --profiles-dir . } finally { Pop-Location }
}
Invoke-Etape "Export JSON" { python (Join-Path $racine 'export.py') }

Write-Host ("=" * 60)
Write-Host ("Pipeline terminé en {0:N1} s" -f $script:total.Elapsed.TotalSeconds) -ForegroundColor Green
exit 0
