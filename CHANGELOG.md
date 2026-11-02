# Changelog

## 0.3.0rc1 (release candidate, not homologated)

Preparation for a first run on real hardware. No record of a physical-printer homologation has been committed, so this is a pre-release. A stable 0.3.0 needs the evidence described in [docs/releasing.md](docs/releasing.md).

- Fix: alert de-duplication compares against the whole day's file. With two unresolved days the messages used to alternate and pile up on every run.
- Fix: the package metadata uses an SPDX license expression. The old form stops building with current setuptools in February 2027.
- Security: on POSIX, `state/`, `out/` and `logs/` are created readable only by their owner. On Windows the folder's ACL applies.
- New: `scripts/check_homologation.py` reads a filled-in checklist and refuses approval while any check lacks a result or evidence, any check failed, or the sign-off is missing.
- New: [docs/releasing.md](docs/releasing.md), the criteria for a stable release.
- CI: actions updated to checkout 7 and setup-python 7. Dependabot no longer raises dependency floors.
- New: `printguard --version`.
- New: `printguard resolve --day YYYY-MM-DD` settles an earlier day.
- New: `run` and `check` write an alert for any earlier day still unresolved, every day, until it is settled.
- New: exit code 5 for an unexpected error. It is logged, written as an alert, and the lock is released.
- Changed: Event Log alerts use `Write-EventLog` with a `printguard` source that `install_task.ps1` registers. `eventcreate` needed administrator rights, and the task runs as a normal user. Verified on a hosted runner as administrator.
- Fix: the journal connection is closed when the schema can't be applied, which left a corrupt `journal.db` locked on Windows.
- CI: read-only token permissions, concurrency control, Dependabot.
- Docs: [installation procedure](docs/installation-windows.md), [homologation checklist](docs/homologation-checklist.md), a security note, release notes for 0.2.1.

## 0.2.1

Windows validation on a hosted runner. See [docs/windows-validation.md](docs/windows-validation.md).

- New CI job `windows-integration`: parses and lints the PowerShell scripts, registers the scheduled task and reads it back, runs the spooler backend against a real paused print queue, and runs the guardian end to end.
- Fix: the guardian no longer aborts on the first stderr line under Windows PowerShell 5.1.
- Fix: PowerShell errors are no longer returned as CLIXML. Scripts are passed encoded, with plain text output.
- Fix: an empty queue printed as `null` by `ConvertTo-Json` is read as empty instead of unreadable.
- The installer resolves the full path of Python. The guardian takes `-ConfirmTimeout`.

## 0.2.0

Safer recovery when a run is interrupted. printguard still cannot prove that paper came out, so this release is about not making things worse when it can't tell.

- New `unknown` day state for attempts whose outcome can't be established. It is never retried automatically and never expires into `falha`.
- Write-ahead journal (`state/journal.db`, SQLite). The attempt is recorded before the printer is called, then updated with the job id.
- Process lock (`state/printguard.lock`). A second `run` exits with code 3 instead of racing the first. The lock belongs to the OS, so a killed process releases it.
- Recovery looks at the journal and the spooler before deciding anything. A job that is still queued is confirmed. A job that is gone, or a queue that can't be read, leaves the day `unknown`.
- New command `printguard resolve --printed | --not-printed` to settle an `unknown` day by hand.
- New exit codes: 3 for "another instance is running", 4 for `unknown`.
- Alerts that repeat the previous message are no longer written again.
- `print-only` refuses to run while an attempt is unresolved. Before, it cancelled the pending job and sent a new one.
- Failing to cancel a stuck job is now `unknown`, since the job may still print. Before, it was a plain failure.
- Fix: SQLite connections are closed, which unblocks the Windows CI.
- State files from 0.1 are picked up on the first run. Day summaries stay in `state/<date>.json`; the journal is the source of truth for recovery.

## 0.1.0

First public version: CLI, per-day state, simulated and Windows spooler backends, PDF report, alert file, scheduled task scripts, CI.
