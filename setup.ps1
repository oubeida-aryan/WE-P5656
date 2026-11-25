$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

if (-not $sourceRoot) { $sourceRoot = $PSScriptRoot }
$installRoot = Join-Path $env:LOCALAPPDATA "WI-PRESENCE"
$appName = "WI-PRESENCE | CNC Staff Presence"
$iconPath = Join-Path $sourceRoot "wi-presence-icon.ico"
$script:installed = $false

$form = New-Object System.Windows.Forms.Form
$form.Text = "WI-PRESENCE | Installation"
$form.StartPosition = "CenterScreen"
$form.ClientSize = New-Object System.Drawing.Size(640, 430)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(246, 249, 252)
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)
if (Test-Path $iconPath) {
    $form.Icon = New-Object System.Drawing.Icon($iconPath)
}

$header = New-Object System.Windows.Forms.Panel
$header.Dock = "Top"
$header.Height = 108
$header.BackColor = [System.Drawing.Color]::FromArgb(7, 28, 51)
$form.Controls.Add($header)

$logo = New-Object System.Windows.Forms.PictureBox
$logo.Location = New-Object System.Drawing.Point(22, 17)
$logo.Size = New-Object System.Drawing.Size(74, 74)
$logo.SizeMode = "Zoom"
if (Test-Path (Join-Path $sourceRoot "wi-presence-icon.png")) {
    $sourceImage = [System.Drawing.Image]::FromFile((Join-Path $sourceRoot "wi-presence-icon.png"))
    $logo.Image = New-Object System.Drawing.Bitmap($sourceImage)
    $sourceImage.Dispose()
}
$header.Controls.Add($logo)

$title = New-Object System.Windows.Forms.Label
$title.Text = "WI-PRESENCE"
$title.ForeColor = [System.Drawing.Color]::White
$title.Font = New-Object System.Drawing.Font("Segoe UI", 22, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(116, 20)
$title.AutoSize = $true
$header.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "Pointage automatique du personnel | CNC"
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(181, 224, 226)
$subtitle.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$subtitle.Location = New-Object System.Drawing.Point(119, 62)
$subtitle.AutoSize = $true
$header.Controls.Add($subtitle)

$welcome = New-Object System.Windows.Forms.Label
$welcome.Text = "Installation du poste de gestion"
$welcome.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$welcome.ForeColor = [System.Drawing.Color]::FromArgb(7, 28, 51)
$welcome.Location = New-Object System.Drawing.Point(32, 132)
$welcome.AutoSize = $true
$form.Controls.Add($welcome)

$description = New-Object System.Windows.Forms.Label
$description.Text = "L'assistant configure WI-PRESENCE, ses dependances et les raccourcis Windows."
$description.ForeColor = [System.Drawing.Color]::FromArgb(83, 103, 122)
$description.Location = New-Object System.Drawing.Point(34, 165)
$description.AutoSize = $true
$form.Controls.Add($description)

$status = New-Object System.Windows.Forms.Label
$status.Text = "Pret a installer"
$status.ForeColor = [System.Drawing.Color]::FromArgb(14, 159, 157)
$status.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$status.Location = New-Object System.Drawing.Point(34, 216)
$status.AutoSize = $true
$form.Controls.Add($status)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Location = New-Object System.Drawing.Point(34, 244)
$progress.Size = New-Object System.Drawing.Size(572, 16)
$progress.Minimum = 0
$progress.Maximum = 100
$progress.Style = "Continuous"
$form.Controls.Add($progress)

$launch = New-Object System.Windows.Forms.CheckBox
$launch.Text = "Lancer WI-PRESENCE a la fin"
$launch.Checked = $true
$launch.ForeColor = [System.Drawing.Color]::FromArgb(42, 59, 74)
$launch.Location = New-Object System.Drawing.Point(34, 282)
$launch.AutoSize = $true
$form.Controls.Add($launch)

$destination = New-Object System.Windows.Forms.Label
$destination.Text = "Installation : " + $installRoot
$destination.ForeColor = [System.Drawing.Color]::FromArgb(105, 122, 138)
$destination.Location = New-Object System.Drawing.Point(34, 313)
$destination.AutoSize = $true
$form.Controls.Add($destination)

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = "Quitter"
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$cancel.FlatStyle = "Flat"
$cancel.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(194, 207, 218)
$cancel.Location = New-Object System.Drawing.Point(414, 360)
$cancel.Size = New-Object System.Drawing.Size(90, 34)
$form.Controls.Add($cancel)

$install = New-Object System.Windows.Forms.Button
$install.Text = "Installer"
$install.FlatStyle = "Flat"
$install.BackColor = [System.Drawing.Color]::FromArgb(34, 211, 209)
$install.ForeColor = [System.Drawing.Color]::FromArgb(7, 28, 51)
$install.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$install.Location = New-Object System.Drawing.Point(512, 360)
$install.Size = New-Object System.Drawing.Size(94, 34)
$form.Controls.Add($install)
$form.AcceptButton = $install
$form.CancelButton = $cancel

function Update-Progress([int]$value, [string]$message) {
    $progress.Value = [Math]::Max(0, [Math]::Min(100, $value))
    $status.Text = $message
    $form.Refresh()
    [System.Windows.Forms.Application]::DoEvents()
}

function Find-Python {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:ProgramFiles "Python312\python.exe"),
        (Join-Path $env:ProgramFiles "Python313\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*WindowsApps*") { return $command.Source }
    return $null
}

function Run-SetupStep([string]$program, [string[]]$parameters) {
    $quoted = ($parameters | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $run = Start-Process -FilePath $program -ArgumentList $quoted -WindowStyle Hidden -PassThru
    try {
        while (-not $run.WaitForExit(150)) {
            [System.Windows.Forms.Application]::DoEvents()
        }
        if ($run.ExitCode -notin 0,3010) {
            throw ("Échec de l’étape « " + $status.Text + " » (code " + $run.ExitCode + ").")
        }
    } finally {
        $run.Dispose()
    }
}

function Create-Shortcut([string]$path, [string]$target, [string]$arguments, [string]$workingDirectory) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $target
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $workingDirectory
    $shortcut.Description = $appName
    $shortcut.IconLocation = (Join-Path $workingDirectory "wi-presence-icon.ico") + ",0"
    $shortcut.Save()
}

$install.Add_Click({
    if ($script:installed) {
        $form.Close()
        return
    }
    $install.Enabled = $false
    $cancel.Enabled = $false
    $form.ControlBox = $false
    try {
        foreach ($required in @("presence.py", "script.js", "requirements.txt", "wi-presence-icon.ico")) {
            if (-not (Test-Path (Join-Path $sourceRoot $required))) {
                throw "Fichier manquant : $required"
            }
        }

        Update-Progress 8 "Preparation du dossier WI-PRESENCE..."
        New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceRoot "presence.py"), (Join-Path $sourceRoot "script.js"), (Join-Path $sourceRoot "requirements.txt"), (Join-Path $sourceRoot "wi-presence-icon.ico") -Destination $installRoot -Force

        Update-Progress 20 "Verification de Python..."
        $python = Find-Python
        if (-not $python) {
            Update-Progress 28 "Telechargement de Python..."
            $pythonInstaller = Join-Path $env:TEMP ("wi-presence-python-" + [guid]::NewGuid().ToString("N") + ".exe")
            Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $pythonInstaller
            $signature = Get-AuthenticodeSignature -LiteralPath $pythonInstaller
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*') {
                throw "La signature du programme Python est invalide."
            }
            Run-SetupStep $pythonInstaller @("/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_test=0")
            $python = Find-Python
        }
        if (-not $python) { throw "Python n'a pas pu etre installe." }

        $venvPython = Join-Path $installRoot "venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            Update-Progress 42 "Creation de l'environnement local..."
            Run-SetupStep $python @("-m", "venv", (Join-Path $installRoot "venv"))
        }
        if (-not (Test-Path $venvPython)) { throw "L'environnement Python n'a pas pu etre cree." }

        Update-Progress 58 "Installation des bibliotheques..."
        Run-SetupStep $venvPython @("-m", "pip", "install", "-r", (Join-Path $installRoot "requirements.txt"), "--disable-pip-version-check")
        Run-SetupStep $venvPython @("-c", "import tkinter, qrcode; from PIL import ImageTk")

        Update-Progress 78 "Creation des raccourcis..."
        $desktop = [Environment]::GetFolderPath("Desktop")
        $startMenu = [Environment]::GetFolderPath("Programs")
        New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
        $pythonw = Join-Path $installRoot "venv\Scripts\pythonw.exe"
        if (-not (Test-Path $pythonw)) { throw "Python Windows n'a pas ete trouve apres l'installation." }
        $arguments = '"' + (Join-Path $installRoot "presence.py") + '"'
        Create-Shortcut (Join-Path $desktop "WI-PRESENCE.lnk") $pythonw $arguments $installRoot
        Create-Shortcut (Join-Path $startMenu "WI-PRESENCE.lnk") $pythonw $arguments $installRoot

        $form.ControlBox = $true
        Update-Progress 100 "Installation terminee"
        $script:installed = $true
        $install.Text = "Fermer"
        $install.Enabled = $true
        if ($launch.Checked -and (Test-Path $pythonw)) {
            Start-Process -FilePath $pythonw -ArgumentList $arguments -WorkingDirectory $installRoot
        }
    } catch {
        $form.ControlBox = $true
        $status.Text = "Installation interrompue"
        $status.ForeColor = [System.Drawing.Color]::FromArgb(200, 30, 58)
        $install.Enabled = $true
        $cancel.Enabled = $true
        [System.Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, "WI-PRESENCE", "OK", "Error") | Out-Null
    }
})

[void]$form.ShowDialog()
$form.Dispose()
