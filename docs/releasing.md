# Releasing

A stable release means the code was run against the target printer and a person signed off the result. A version that hasn't been through that is a release candidate and is published as a pre-release.

## Stable release criteria

All of these, in this order:

1. **CI is green** on the exact commit: Ubuntu and Windows on Python 3.11 and 3.12, plus `windows-integration`.
2. **A filled homologation record is committed** as `docs/homologation/v<version>.md`, made by copying [homologation-checklist.md](homologation-checklist.md) and filling it in. Leave the template blank.
3. **The record passes the verifier:**
   ```bash
   python scripts/check_homologation.py docs/homologation/v<version>.md
   ```
   It exits 0 only if every record field is filled, every check has a result and evidence, nothing is marked `FAIL`, and the sign-off says approved. Anything else exits 1 and lists what is missing. It checks that the record is complete. It can't check that the evidence is true, so a person has to read it.
4. **The version is consistent.** `pyproject.toml` and `src/printguard/__init__.py` carry the release version, with no `rc` or `dev` suffix, and `CHANGELOG.md` has a dated section for it.
5. **The release notes** are in `docs/releases/v<version>.md` and state the printer model, the PDF application and the Windows version it was homologated with, plus any conditions from the sign-off.

## Evidence

Evidence is whatever lets someone else see the result: a log line, an exit code, `Get-ScheduledTaskInfo` output, a photo of the page. Keep it outside the repository if it contains real report data, printer names on a private network or user names, and name the files in the Evidence column. Redact before committing anything.

## Publishing

```bash
git tag -a v<version> <commit> -m "printguard <version>"
git push origin v<version>
gh release create v<version> --title "printguard <version>" --notes-file docs/releases/v<version>.md
```

For a release candidate add `--prerelease` and say in the notes that it is not homologated.

## After a failed homologation

A `FAIL` in the record blocks the release. Fix the cause, add a test that reproduces it where one is possible, bump the candidate (`rc2`), and repeat only the scenarios the fix could affect plus the ones the checklist marks as always repeated: 2.1, 3.1, 3.6, 4.3 and 6.2. Keep the failed record. It is the history of why the fix exists.
