$ErrorActionPreference = "SilentlyContinue"

# Short two-tone alert for Codex permission prompts.
[Console]::Beep(880, 180)
Start-Sleep -Milliseconds 80
[Console]::Beep(1175, 260)
