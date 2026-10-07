param([string]$DataDir = '')
Set-Location -LiteralPath $PSScriptRoot
if ($DataDir) {
    conda run --no-capture-output -n pyqt python main.py --data-dir $DataDir
} else {
    conda run --no-capture-output -n pyqt python main.py
}
