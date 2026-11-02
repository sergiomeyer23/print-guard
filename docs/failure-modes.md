# Failure modes

What printguard does for each failure, and what it can't do. "Test" names the file that injects the fault.

| Failure | Typical cause | Behavior | Test |
|---|---|---|---|
| Job stuck in queue | Printer offline, paper jam, driver hang | Wait for the confirm timeout, cancel, state `falha`, alert. Next run resubmits. | `test_runner` |
| Cancel refused | Permissions, job already moving | State `unknown`. The job may still print, so there is no reprint. | `test_reliability` |
| Two runs at once | Overlapping triggers, manual run during a scheduled one | The second exits with code 3, writes nothing, sends nothing. | `test_reliability` |
| Process killed before the send | Power cut, task killed | The journal has an intent and no job id. Nothing proves a send, so `unknown`. No automatic resend. | `test_reliability` |
| Process killed right after the send | Same | If the job is still queued the next run finds it by document name and confirms it. If it already finished, `unknown`. | `test_reliability` |
| Reboot with an `unknown` day | Windows update | Stays `unknown` run after run, with a single alert line. A person runs `resolve`. | `test_reliability` |
| Queue unreadable during a live run | Spooler restarting, RPC errors | State stays `enviado`, no resubmit, alert. A later run confirms. | `test_runner` |
| Queue unreadable during recovery | Spooler still down after reboot | State `unknown`, no resubmit. When the queue returns and the job is still there, it is confirmed. | `test_reliability` |
| Stale lock after a crash | Killed process | Nothing to clean up: the OS drops the lock with the process, and a leftover lock file is ignored. | `test_reliability` |
| Truncated or empty PDF | Disk full, process killed while writing | The report is written to a `.part` file and renamed, and the structure is checked again before sending. A bad file is never submitted. | `test_runner` |
| Duplicate print from a rerun | Task triggers overlap, manual rerun | `ok` days are skipped, `enviado` days are confirmed instead of resent. | `test_runner` |
| Source database missing or locked | Share unavailable, file moved | Report build fails, state `falha`, alert, retry on the next run. | `test_runner` |
| Corrupt state file | Disk problem | Moved to `.corrupt`. If the journal knows the day, its state is rebuilt from it. | `test_runner`, `test_reliability` |
| State file and journal disagree | Crash between the two writes | The journal wins and the state file is rewritten. | `test_reliability` |
| Machine asleep at 08:00 | Power settings | `WakeToRun` plus the boot trigger. Not testable in CI. | none |
| Job accepted then dropped by the printer | Firmware, network printers | Looks identical to success. printguard can't see past the spooler. | none |
| Job finished, then the run died | Fast printer, killed process | Printed and lost look the same once the job leaves the queue, so the day is `unknown` and gets a `resolve`. This costs an operator decision on a report that printed. | `test_reliability` |
| Wrong default PDF handler | No handler supports `PrintTo` | Starting the print fails, which is a proven rejection: `falha`, alert. | `test_spooler` |
| Document renamed by the handler | Some PDF viewers | Recovery can't match the job by name and falls back to `unknown`. | none |
| Two machines on one shared folder | Network share as workdir | Not protected. The lock is per machine. | none |
| Event Log write denied | No admin rights to create the source | The alert file is still written. | none |
