**Automatic Git Bidirectional Sync (LaunchAgent)**

Purpose
-------

This document describes the user-level launchd agent that performs an automatic, once-per-24-hour bidirectional Git sync for the repository copy at ~/.sync/repos/CSV-to-ASC. It lists the components, expected behaviour, where logs are written, and safe commands to inspect, disable, or re-enable the service.

Components & locations
----------------------

- LaunchAgent plist: `~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist`
- Sync script: `~/.sync/git-bidirectional-sync.sh`
- Repository target (LaunchAgent now points to workspace): `/Users/mddexter/GitHub Repos/CSV-to-ASC`
- Logs directory: `~/.sync/logs/` (files like `sync_YYYYMMDD_HHMMSS.log`)

Schedule
--------

- The LaunchAgent plist sets `StartInterval` to `86400` seconds (24 hours).
- `RunAtLoad` is set to `true`, so the script runs at load as well as on the interval.

Behavior
--------

- On each run the script performs:
  1. `git fetch` from origin
  2. Merge-base checks and a test-merge to detect conflicts
  3. `git pull` from the remote branch (usually `main`)
  4. If local uncommitted or unpushed changes exist, it stages, commits with an "Auto-sync" message, and `git push`es them
  5. Logs actions and writes conflict details if a merge conflict is detected; in that case the script aborts and exits non-zero for manual resolution

Safety notes
------------

- The agent operates on the specified repository path (by default previously `~/.sync/repos/CSV-to-ASC`). It now targets your workspace at `/Users/mddexter/GitHub Repos/CSV-to-ASC`, so automated pulls/commits will affect the copy you edit in your editor. Confirm paths before making changes.
- Commits created by the script use a generic commit message: `Auto-sync: YYYY-MM-DD HH:MM:SS`.
- If a merge conflict is detected the script will abort and record conflict details to `~/.sync/logs/conflicts_*.log` for manual resolution.
- Git credentials used are whatever the Git environment and credential helpers provide (SSH keys, macOS Keychain credential helpers, or cached credentials). Be careful when sharing or modifying the script so you don't expose secrets.

Inspecting recent activity
-------------------------

Show most recent logs:

```bash
ls -la ~/.sync/logs
tail -n 200 ~/.sync/logs/sync_*.log
```

View current LaunchAgent status:

```bash
launchctl list | grep com.user.git-bidirectional-sync || true
```

Safe management commands
------------------------

Stop the agent now (unload):

```bash
launchctl unload ~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist
```

Disable it (backup the plist so it can be restored):

```bash
mv ~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist \
   ~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist.bak
```

Re-enable (restore & load):

```bash
mv ~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist.bak \
   ~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist
launchctl load ~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist
```

Remove or archive the script and logs (if you want to preserve data before deleting):

```bash
mv ~/.sync ~/.sync.backup
```

Adjusting the schedule
----------------------

- To change the run interval, edit the `StartInterval` integer in the plist and reload the LaunchAgent with `launchctl unload` and `launchctl load`.
- If you prefer a different scheduler (cron, or a manual LaunchAgent with `StartCalendarInterval`), update the plist accordingly.

Recommendations
---------------

- Keep this document in the repository for future reference.
- If you want the sync to operate on the workspace copy instead of `~/.sync/repos/CSV-to-ASC`, modify the LaunchAgent `ProgramArguments` and `WorkingDirectory` to point to the desired path and test manually before letting launchd run it.
- Consider restricting automatic commits or disabling auto-commit if you prefer manual review before pushing.

Questions / Next steps
---------------------

- Would you like me to commit this file to the repository branch for you, or make any edits (more details, example logs, or screenshots)?
Recent changes (2026-06-22)
--------------------------

- Backed up the original LaunchAgent plist to `~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist.bak`.
- Updated `~/Library/LaunchAgents/com.user.git-bidirectional-sync.plist` to point `ProgramArguments` and `WorkingDirectory` at `/Users/mddexter/GitHub Repos/CSV-to-ASC` so the agent now operates directly on your workspace.
- Reloaded the LaunchAgent with `launchctl unload` / `launchctl load` and confirmed it is loaded (`launchctl list` shows `com.user.git-bidirectional-sync`).
- Ran the sync script manually against the workspace; the run completed successfully and wrote a log to `~/.sync/logs/sync_20260622_232345.log`.
- Updated this document to reflect the new target and recorded the change log here.

Would you like me to add example log output or further notes about restoring the original plist? 
