$ErrorActionPreference = 'Stop'
$frontendPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../frontend'))
if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    throw 'Flutter no está en el PATH. Sigue README.md y reinicia la terminal.'
}
Push-Location $frontendPath
try {
    # --no-overwrite conserva el código existente de esta etapa.
    flutter create --no-overwrite --no-pub --platforms=windows,android --project-name=rosen_stock_manager .
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron generar las plataformas.' }
    # El test de contador de la plantilla no corresponde a esta aplicación.
    $templateTest = Join-Path $frontendPath 'test/widget_test.dart'
    if (Test-Path -LiteralPath $templateTest) {
        $content = Get-Content -LiteralPath $templateTest -Raw
        if ($content -match 'Counter increments smoke test') {
            Remove-Item -LiteralPath $templateTest
        }
    }
    flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'Falló la resolución de dependencias.' }
    flutter analyze
    if ($LASTEXITCODE -ne 0) { throw 'El análisis detectó problemas.' }
} finally {
    Pop-Location
}
