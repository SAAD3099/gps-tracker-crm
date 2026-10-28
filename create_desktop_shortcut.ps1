$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop 'Concept Tracking CRM.lnk'
$launcher = Join-Path $project 'launch.bat'
$iconPath = Join-Path $project 'static\concept_tracking.ico'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $env:ComSpec
$shortcut.Arguments = '/c ""' + $launcher + '""'
$shortcut.WorkingDirectory = $project
$shortcut.Description = 'Open Concept Tracking Server Pvt. Ltd. CRM'
$shortcut.IconLocation = $iconPath + ',0'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Host "Created: $linkPath"
