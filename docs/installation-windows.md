# Installing and validating on Windows

A procedure for putting printguard on a real Windows machine with a physical printer, in an order that can't print the wrong thing or hide a problem. It has been written but **not yet followed on real hardware**. Nothing here is a test result.

Plan for an hour the first time. Do it on a day when a stray page of fictional data on the printer is fine.

## 0. Before you start

You need:

- Windows 10, Windows 11 or Windows Server 2016 or newer, with Windows PowerShell 5.1 (it ships with Windows).
- Python 3.11 or newer, 64-bit. Note the full path to `python.exe`.
- The printer installed, with its normal driver, and able to print a test page from Windows.
- A PDF application that handles the shell `PrintTo` verb for the account that will run the task. Adobe Acrobat Reader and SumatraPDF are the usual candidates, and neither has been tested with printguard. Step 5 checks this.
- A folder that is **not** synced or shared. Examples below use `C:\printguard`.

Keep a copy of the checklist open ([homologation-checklist.md](homologation-checklist.md), copied to `docs/homologation/v<version>.md`). Fill it in as you go, with evidence.

## 1. Install

From a checkout of the release you are validating (check out the tag, not a branch):

```powershell
mkdir C:\printguard
python -m venv C:\printguard\venv
C:\printguard\venv\Scripts\python.exe -m pip install .
C:\printguard\venv\Scripts\printguard.exe --version
```

Write the version down. It goes in the homologation record.

## 2. Create and lock down the working directory

```powershell
mkdir C:\printguard\work
icacls C:\printguard\work /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" "Administrators:(OI)(CI)F"
```

Reports contain whatever your data source returns. Only the account that runs the task and administrators should be able to read them. Never put this folder on a network share: the lock only protects one machine.

## 3. Rehearse with the simulated printer, in a separate folder

```powershell
C:\printguard\venv\Scripts\printguard.exe seed --workdir C:\printguard\rehearsal
C:\printguard\venv\Scripts\printguard.exe run  --workdir C:\printguard\rehearsal
C:\printguard\venv\Scripts\printguard.exe check --workdir C:\printguard\rehearsal
```

Expect exit code 0 and a PDF in `C:\printguard\rehearsal\out`. Use a separate folder on purpose. A day recorded as `ok` is never printed again, so a rehearsal in the real working directory would make the real run do nothing.

## 4. Find the exact printer name

```powershell
Get-Printer | Select-Object Name, DriverName, PortName, PrinterStatus
```

Use the `Name` column exactly, spaces and capitals included. A wrong name shows up as an unreadable queue.

## 5. Check the PDF handler without printguard

Use the PDF from step 3:

```powershell
Start-Process -FilePath "C:\printguard\rehearsal\out\report_<date>.pdf" -Verb PrintTo -ArgumentList '"<printer name>"'
```

A page should come out. If PowerShell says "No application is associated", install or associate a PDF application first. If it prints, note which application did it, then look at the queue while the job is there, ideally with the printer paused:

```powershell
Get-PrintJob -PrinterName "<printer name>" | Select-Object Id, DocumentName, JobStatus
```

Recovery after a crash finds jobs by looking for the PDF file name inside `DocumentName`. If the document name doesn't contain it, recovery will end in `unknown` instead of finding the job. Record what you see.

## 6. First real print, still with sample data

```powershell
C:\printguard\venv\Scripts\printguard.exe seed --workdir C:\printguard\homologation
C:\printguard\venv\Scripts\printguard.exe run  --workdir C:\printguard\homologation --printer spooler --printer-name "<printer name>" --confirm-timeout 120
C:\printguard\venv\Scripts\printguard.exe check --workdir C:\printguard\homologation
```

Expect a printed page, exit code 0, and `status: ok` in `state\<date>.json`. Run `run` again. Nothing should print.

If the exit code is 4, read the alert file in `out\`. `unknown` here means printguard could not tell whether the page printed. Look at the printer, then settle it with `printguard resolve`.

## 7. Wire in your own data

Replace `fetch_pending` in `src\printguard\source.py` and the table in `src\printguard\report.py`, reinstall, and repeat step 3 and step 6 in new folders with real data. Do this before installing the task, or the task will print the fictional sample every morning.

## 8. Run the failure scenarios

Work through section 3 of the checklist: stuck job, spooler stopped, process killed, `unknown`, concurrent runs. Give each scenario a fresh working directory. Don't clean a directory by deleting `state\journal.db` as a shortcut. That file is what stops a duplicate print.

## 9. Install the scheduled task

From an elevated PowerShell, so the event source can be registered:

```powershell
cd <checkout>
.\scripts\install_task.ps1 -PrinterName "<printer name>" -Workdir C:\printguard\work -Python C:\printguard\venv\Scripts\python.exe
```

The task is registered for the current user and runs only while that user is logged on. If you need unattended runs, change that in Task Scheduler ("Run whether user is logged on or not") and record the result: the `PrintTo` verb may behave differently without a desktop session, and that has not been tested.

Start it once by hand and read the result:

```powershell
Start-ScheduledTask -TaskName printguard
Get-ScheduledTaskInfo -TaskName printguard
Get-Content C:\printguard\work\logs\guard_*.log
```

Then follow section 6 of the checklist for the timed triggers.

## 10. Operating it

| You want to | Do this |
|---|---|
| See today's state | `printguard check --workdir C:\printguard\work`. Exit code 0 ok, 1 falha, 2 pending, 3 busy, 4 unknown, 5 error |
| See why it failed | The newest `out\ALERTA_<date>.txt`, `logs\guard_<date>.log`, and the Application event log source `printguard` |
| Settle an `unknown` | Look at the printer. `printguard resolve --printed` if the page is there, `--not-printed` if it isn't. Add `--day` for an earlier day |
| Reprint a page | `printguard print-only`. It refuses while an attempt is unresolved |
| Upgrade | Copy `state\` somewhere safe, `pip install` the new release, read its CHANGELOG, run `check`. Settle every `unknown` first |
| Remove it | `Unregister-ScheduledTask -TaskName printguard -Confirm:$false`, then delete the working directory. `Remove-EventLog -Source printguard` from an elevated prompt removes the event source |

## What this procedure cannot promise

A job leaving the Windows queue means the spooler is finished with it, not that paper came out. A printer that accepts a job and drops it looks like success. That is why the first weeks should include someone checking that the paper is there.
