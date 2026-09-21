# Agent instructions

## Ship / push / deploy (mandatory)

When the user says **ship**, **push**, **deploy**, **put on main**, **release**, **publish**, **gh**, **rh**, or similar:

1. Read **`C:\Users\david\.agents\SHIP.md`**
2. **RoutineHub first.** If they gave an `icloud.com/shortcuts/` URL or said rh, run that before any git:

```powershell
python -X utf8 $env:USERPROFILE\.agents\shortcut-rh.py --repo free-everything-downloader --link <icloud-url> --version <X.Y> --changes "<no emojis>"
```

That creates the version first. Get Shortcut must already be that version before any listing copy is posted. Never listing-only. Never leave users on an older download while the page claims a newer build.

3. Then GitHub: `powershell -File $env:USERPROFILE\.agents\ship.ps1 -Repo free-everything-downloader -SkipRh [-Message "..."]` (or pass `-ICloudLink` if RH is not done yet so step 0 runs inside the script)

**Pipeline after RH:** Commit on Laboratory → Push `origin main` → Backup 7z to `D:\BACKUP\CODE Backups\free-everything-downloader\`  
Pattern: `free-everything-downloader_YYYY-MM-DD_<sha>_<slug>.7z` (exclude target, .git, node_modules, dist, .next)

Never bare-push without backup. Report RH version, commit, remote, and full backup path.

RoutineHub is not inside a generic `ship.ps1` run with no iCloud link. Apple mints iCloud share links on a real iPhone or iPad.

The on-device install path is Files → Drive → My Drive → `FREE Media Downloader.shortcut`. HubSign writes that file to `H:\My Drive`. Do not drop it in iCloud Drive.
