# Homologation checklist

Acceptance checklist for running printguard against a physical printer. **Status: not executed.** Nothing in this file is a result. Every box is empty until a person has done the step on the real machine and written down what they saw.

Don't fill in this file. Copy it to `docs/homologation/v<version>.md` and fill in the copy, so the template stays blank. [releasing.md](releasing.md) explains how the record gates a stable release, and `python scripts/check_homologation.py <record>` lists what is still missing.

Follow [installation-windows.md](installation-windows.md) for the setup. Use a fresh working directory for each scenario, so one scenario's state can't affect the next.

## Record

| Field | Value |
|---|---|
| printguard version (`printguard --version`) | |
| Git tag or commit | |
| Windows version | |
| Python version | |
| Printer model and driver | |
| Printer connection (USB, network, shared) | |
| PDF application used for `PrintTo` | |
| Tested by | |
| Date | |

## How to mark a step

Write one of `PASS`, `FAIL` or `N/A` in the Result column, and put the evidence (a log line, an exit code, a photo of the paper, a screenshot) in the Evidence column. A step with no evidence is not done.

## 1. Environment

| # | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| 1.1 | `printguard --version` after install | Prints the version being validated | | |
| 1.2 | Rehearsal with the simulated printer in a separate folder | Exit 0, PDF created, second run prints nothing | | |
| 1.3 | `Start-Process -Verb PrintTo` with the rehearsal PDF | A page comes out. Record the PDF application | | |
| 1.4 | `DocumentName` of a queued job (printer paused) | Contains the PDF file name. If not, recovery will fall back to `unknown`: record the exact name | | |
| 1.5 | Working directory permissions | Only the task account and administrators can read it | | |

## 2. Printing the PDF

| # | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| 2.1 | `run --printer spooler` with sample data | One page on paper, exit 0, state `ok`, job gone from the queue | | |
| 2.2 | Look at the page | A4, the "Queried at" time in the header matches the run, table readable, no cut-off columns | | |
| 2.3 | A report longer than one page | Header and column titles repeat on every page, page numbers correct | | |
| 2.4 | An empty report (no rows) | Prints a page saying 0 shipments, no crash | | |
| 2.5 | `run` again the same day | Exit 0, nothing printed | | |
| 2.6 | `print-only` | A second copy, new job id, source not queried | | |
| 2.7 | Real data through your own `source.py` and `report.py` | The numbers match the source system for the same day | | |

## 3. Failures and recovery

Each scenario starts from a clean working directory and ends with a count of the pages that actually came out.

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 3.1 | Stuck job | Pause the printer (or take it offline), `run --confirm-timeout 10` | Exit 1, job cancelled and gone from the queue, state `falha`, one line in the alert file. Resume the printer, `run` again: exactly one page | | |
| 3.2 | Printer error | Open the cover or pull the paper, `run` | Job reported as error, cancelled, `falha`. Fix, `run`: one page | | |
| 3.3 | Spooler stopped during a run | Pause the printer, `run` in one window, `Stop-Service Spooler` in another | Exit 1 or 4, alert, nothing printed twice. `Start-Service Spooler`, `run`: the job is confirmed or the day is `unknown`. Record which | | |
| 3.4 | Process killed after the send | Pause the printer, `run`, as soon as the job is in the queue `Stop-Process` the python process | State `enviado`. Resume the printer, `run`: the job is found, confirmed, one page | | |
| 3.5 | Process killed before the send | Same, but kill earlier (hard to hit by hand; try a few times or note that you couldn't) | Day becomes `unknown`, nothing printed twice | | |
| 3.6 | Job vanishes | After 3.4, remove the job with `Remove-PrintJob` instead of resuming, then `run` | Exit 4, state `unknown`, alert once. A second `run` prints nothing | | |
| 3.7 | Concurrent runs | Pause the printer, start `run` with `--confirm-timeout 60`, start a second `run` in another window | Second one exits 3 at once, only one job in the queue | | |
| 3.8 | Lock after a kill | Kill a `run` mid-wait, then run again | Not stuck on the lock | | |
| 3.9 | PDF handler missing | Remove the association, or use a user without one | Exit 1, "No application is associated", state `falha`, alert | | |

## 4. The `unknown` state

| # | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| 4.1 | From 3.6, run `run` three times | Always exit 4, nothing printed, one alert line, not three | | |
| 4.2 | `print-only` while `unknown` | Refuses with exit 4, nothing printed | | |
| 4.3 | `resolve --not-printed`, then `run` | Exactly one new page, state `ok` | | |
| 4.4 | Repeat 3.6, then `resolve --printed` | State `ok`, nothing printed, later runs print nothing | | |
| 4.5 | Leave a day `unknown`, advance the clock a day (or run the next day) | `run` and `check` alert about the earlier day. `resolve --day` closes it | | |
| 4.6 | Nothing turns `unknown` into `falha` by itself | Leave it for a full 09:05 window | | |

## 5. Restart

| # | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| 5.1 | Job queued and printer paused, reboot Windows, don't touch anything | Record whether the spooler still has the job after boot | | |
| 5.2 | After 5.1, the boot trigger fires 5 minutes after startup | The guardian runs and the job is confirmed, or the day is `unknown`. Nothing printed twice | | |
| 5.3 | Reboot with the day already `ok` | Nothing happens, nothing prints | | |
| 5.4 | Reboot with no state for the day (machine was off at 08:00) | The boot trigger prints the report once | | |

## 6. Scheduled task

| # | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| 6.1 | `Get-ScheduledTask` after install | Daily 08:00, repeat every 5 minutes for 1h05, boot +5 minutes, wake to run, one instance at a time | | |
| 6.2 | `Start-ScheduledTask` by hand | Report prints, `Get-ScheduledTaskInfo` shows result 0, a guard log exists | | |
| 6.3 | The 08:00 run happens on its own | Record the time it actually started | | |
| 6.4 | Repetition stops once the day is `ok` | Later runs exit at once ("already confirmed") | | |
| 6.5 | Repetition with the printer off | One alert line, retries every 5 minutes, nothing duplicated, stops at 09:05 | | |
| 6.6 | Wake from sleep | The machine wakes and the report prints. Note whether it needed a power or BIOS setting | | |
| 6.7 | Logged off or screen locked | Record exactly what happens. The task is registered for an interactive user, and this has not been tested | | |
| 6.8 | Alerts reach the Event Log as a standard user | An entry from source `printguard` appears in the Application log | | |
| 6.9 | Uninstall | Task removed, no leftover triggers | | |

## 7. Run it for a while

| # | Check | Expected | Result | Evidence |
|---|---|---|---|---|
| 7.1 | Five working days of real use | Every day has a page on paper and a state of `ok` | | |
| 7.2 | Someone confirms the paper each day | No day marked `ok` without a page | | |
| 7.3 | Disk use after the period | `out\`, `state\` and `logs\` sizes recorded | | |

## Sign-off

The sign-off belongs to a person, not to this file.

| Decision | Name | Date |
|---|---|---|
| Approved for real use / approved with conditions / not approved | | |

Conditions or open problems:
