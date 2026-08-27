# Agent instructions

## Ship / push / deploy (mandatory)

When the user says **ship**, **push**, **deploy**, **put on main**, **release**, **publish**, or similar:

1. Read and execute **`C:\Users\david\.agents\SHIP.md`**
2. Or run: `powershell -File $env:USERPROFILE\.agents\ship.ps1 -Repo free-everything-downloader [-Message "..."]`
3. Skill: `ship-deploy`

**Pipeline for this repo:** Commit on Laboratory → Push `origin main` → Backup 7z to `D:\BACKUP\CODE Backups\free-everything-downloader\`  
Pattern: `free-everything-downloader_YYYY-MM-DD_<sha>_<slug>.7z` (exclude target, .git, node_modules, dist, .next)

Never bare-push without backup. Report commit + remote + full backup path.

## RoutineHub is not part of ship

Do **not** publish, version, or rewrite the RoutineHub listing from `ship.ps1` or from a generic ship. RoutineHub (listing copy, HubSign, iCloud share link, versions/create) is a separate, explicit step. Apple will only mint an iCloud share link on a real iPhone or iPad.

The on-device install path is Files → iCloud Drive → Documents → `Free EVERYTHING Downloader.shortcut`.
