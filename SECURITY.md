# Security policy

## Supported versions

Pre-1.0: the latest commit on the default branch receives fixes.

## Reporting a vulnerability

Please report suspected vulnerabilities privately via the repository's issue
tracker security contact, or to the maintainers directly, rather than opening
a public issue with exploit details.

## Data-handling posture

`rosterops` is a local-first library and CLI:

- It performs **no network access** during processing and never uploads roster
  data anywhere.
- It **never modifies input files**; all writes go to the configured output
  directory, with explicit overwrite protection.
- Configuration files are parsed with `yaml.safe_load` only — they cannot
  execute code, shell commands, or imports.
- Logs and run metadata avoid full employee rows; identifiers are preferred
  over names in summaries.

Roster inputs routinely contain personal information. Treat input and output
files as sensitive: restrict filesystem permissions, avoid committing real
data to version control, and follow your organization's retention policy for
generated reports.
