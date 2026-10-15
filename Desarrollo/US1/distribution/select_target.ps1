param([ValidateSet('apply', 'restore')][string]$Mode = 'apply')
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Windows.Forms
    Write-Host 'Cierra Fiji y la biblioteca de Cavity Light antes de continuar.'
    $targetDialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $targetDialog.Description = 'Selecciona la carpeta CavityLight que contiene Fiji y Python.'
    $targetDialog.ShowNewFolderButton = $false
    if ($targetDialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }
    $selectedTarget = $targetDialog.SelectedPath
    $targetDialog.Dispose()
    $pythonPath = Join-Path $selectedTarget 'Python\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw 'La carpeta seleccionada no contiene Python\python.exe. Selecciona CavityLight.'
    }
    $updaterPath = Join-Path $PSScriptRoot 'updater.py'
    if ($Mode -eq 'apply') {
        & $pythonPath -I -B $updaterPath apply --target $selectedTarget --distribution $PSScriptRoot
    } else {
        $backupDialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $backupDialog.Description = 'Selecciona la copia usability_... dentro de Copias_configuracion.'
        $backupDialog.SelectedPath = Join-Path $selectedTarget 'Copias_configuracion'
        $backupDialog.ShowNewFolderButton = $false
        if ($backupDialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }
        $selectedBackup = $backupDialog.SelectedPath
        $backupDialog.Dispose()
        & $pythonPath -I -B $updaterPath restore --target $selectedTarget --backup $selectedBackup
    }
    exit $LASTEXITCODE
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message)
    exit 1
}
