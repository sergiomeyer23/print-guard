# Failure modes

What printguard does for each failure, and what it can't do.

| Failure | Typical cause | Behavior | Covered by test |
|---|---|---|---|
| Job stuck in queue | Printer offline, paper jam, driver hang | Wait for the confirm timeout, cancel, state `falha`, alert. Next run resubmits. | yes |
| Queue unreadable | Spooler service restarting, RPC errors, corrupt spool file | State stays `enviado`, no resubmit, alert. A later run confirms the same job. | yes |
| Reboot after submit | Windows update, power cut | State file already says `enviado` with the job id, so the next run confirms it. If the job vanished with the reboot, the queue shows nothing and the job counts as done (see below). | yes |
| Truncated or empty PDF | Disk full, process killed while writing | The report is written to a `.part` file and renamed, and the structure is checked again before sending. A bad file is never submitted. | yes |
| Duplicate print | Task triggers overlap, manual rerun | `ok` days are skipped, `enviado` days are confirmed instead of resent. | yes |
| Source database missing or locked | Share unavailable, file moved | Report build fails, state `falha`, alert, retry on the next run. | yes |
| Corrupt state file | Disk problem | Moved to `.corrupt`, day treated as new. This can cause one extra print. | yes |
| Machine asleep at 08:00 | Power settings | `WakeToRun` plus the boot trigger. Not testable in CI. | no |
| Job accepted then dropped by the printer | Firmware, network printers | Looks identical to success. printguard can't see past the spooler. | no |
| Job disappears with a reboot | Spooler cleared on restart | Indistinguishable from a finished job, so the day is marked `ok` with nothing printed. | no |
| Crash between submit and state write | Process killed in a tiny window | Next run may print a second copy. | no |
| Wrong default PDF handler | No handler supports `PrintTo` | Submit fails with "no new job appeared", state `falha`, alert. | partly |
| Event Log write denied | No admin rights to create the source | The alert file is still written. | no |
