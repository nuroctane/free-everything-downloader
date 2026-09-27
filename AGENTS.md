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

## Shortcut release prep (do this automatically)

For every release candidate, before asking the user for an iCloud link:

1. Run the local validation, audit, and extractor test gates.
2. Run `python -X utf8 scripts\sign.py`.
3. Verify `H:\My Drive\FREE Media Downloader.shortcut` exists and starts with the `AEA1` HubSign header.
4. Tell the user to install it from Files → Drive → My Drive, then copy a fresh iCloud link from the installed shortcut.

The signed Drive artifact is the handoff for device testing. Do not ask the user to upload files or search iCloud Documents. Do not inspect Cursor sessions, transcripts, or Cursor state unless the user explicitly asks for that.

If no fresh iCloud link exists yet, stop after the Drive handoff; do not commit, push, create a RoutineHub version, or claim the release is shipped. Once the user supplies the link, run the RoutineHub-first flow above, then GitHub and backup.

**Pipeline after RH:** Commit on Laboratory → Push `origin main` → Backup 7z to `D:\BACKUP\CODE Backups\free-everything-downloader\`  
Pattern: `free-everything-downloader_YYYY-MM-DD_<sha>_<slug>.7z` (exclude target, .git, node_modules, dist, .next)

Never bare-push without backup. Report RH version, commit, remote, and full backup path.

RoutineHub is not inside a generic `ship.ps1` run with no iCloud link. Apple mints iCloud share links on a real iPhone or iPad.

The on-device install path is Files → Drive → My Drive → `FREE Media Downloader.shortcut`. HubSign writes that file to `H:\My Drive`. Do not drop it in iCloud Drive.
