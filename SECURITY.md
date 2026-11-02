# Security

printguard runs on a schedule, reads a data source, writes files and talks to the Windows print spooler. It has no network code, no web server and no credentials of its own.

## What to protect

- **The working directory.** `out/` holds the rendered reports, which contain whatever your data source returns. `state/` holds the journal and day files, and `logs/` holds the guardian logs. Restrict the folder to the account that runs the task and to administrators.
- **The data source.** The sample reads a local SQLite file. If you point it at a real source, keep its credentials outside the repository and outside the working directory.
- **The scheduled task.** It runs as the user who installed it. Don't run it with more privilege than printing needs.

## Reporting a problem

Open a GitHub issue describing the problem. Don't paste report contents, printer names from a private network or logs from a real environment. If you need to share those, say so in the issue and I'll arrange another way.

## Supported versions

Only the latest release is looked after.
