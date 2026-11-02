# Windows validation

What has been checked on Windows, where, and what has not. The "windows-integration" job in CI runs all of it on a GitHub-hosted `windows-latest` runner. No physical printer has been involved at any point.

## Checked on a hosted Windows runner

| What | How | Result |
|---|---|---|
| The `.ps1` scripts parse under Windows PowerShell 5.1 | `tests/windows/check_scripts.ps1`, PowerShell parser | passes |
| Static analysis of the scripts | PSScriptAnalyzer, errors and warnings | no findings after fixes (it flagged three issues in the first run) |
| `install_task.ps1` registers the task as documented | The registered task is read back: two triggers, daily 08:00, repeat every 5 minutes for 1h05, boot trigger delayed 5 minutes, `WakeToRun`, `StartWhenAvailable`, `IgnoreNew` | passes |
| Queue listing and parsing of `Get-PrintJob` output | A real spooler queue, empty and with a job in it | passes |
| Cancelling a job, and cancelling one that doesn't exist | `Remove-PrintJob` against a paused test printer | passes |
| Sending a file through the `PrintTo` verb and finding the new job id | A `.txt` file handled by Notepad | passes |
| Stuck job on a real queue is cancelled and the day becomes `falha` | Runner with `WindowsSpoolerPrinter` | passes |
| A job id that is not in the queue leaves the day `unknown` | Same | passes |
| Unknown printer name reads as an unreadable queue | Same | passes |
| The guardian script runs to the end under PowerShell 5.1 and leaves a log and an alert | `tests/windows/smoke_guardian.ps1` | passes |

The test printer is "Microsoft Print To PDF" on a file port and is paused, so jobs stay in the queue instead of being printed.

## Found by this validation

- Windows PowerShell 5.1 turns native stderr lines into terminating errors under `$ErrorActionPreference = "Stop"`. The guardian would have aborted on its first log line. Fixed.
- Scripts passed with `-EncodedCommand` return errors as CLIXML, which made alert messages unreadable. Fixed, with a test built from the real output.
- A Windows runner has no PDF application registered for `PrintTo`. The backend reported that as a proven rejection (`falha` plus an alert), which is the intended behavior, but it shows the prerequisite below.

## Not checked

- Anything involving a physical printer, a network printer or a vendor driver.
- `PrintTo` for PDF files. The runner has no PDF handler, so the path that sends the report itself was exercised only with a text file. Adobe Reader, SumatraPDF and similar programs register the verb differently, and some rename the spool document, which would push recovery to `unknown`.
- The task actually firing at 08:00, waking the machine, repeating until 09:05, or running at boot. Only the registered configuration was read back.
- Running while no one is logged on. The installer registers the task for the current user.
- Writing to the Windows Event Log with `--event-log`. The guardian passes the flag, but whether the entry was written was not verified.
- Spooler behavior across a real reboot.

## Before relying on it

Print a test report on the real printer with `printguard run --printer spooler --printer-name "<name>"`, check the PDF handler first (`printguard run` will report `falha` with "No application is associated" if there is none), and leave the scheduled task in place for a few days while reading `logs/` and the alert files.
