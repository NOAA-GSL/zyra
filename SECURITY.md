# Reporting security issues

- Private reporting: Use GitHub Security Advisories (Security > Report a
  vulnerability). Please do not open public issues or PRs containing exploit
  details.
- What to include: affected version/commit, minimal reproducer or PoC,
  expected/actual impact, and environment details (OS, Python, config).
- Response: Maintainers acknowledge within 3 business days and coordinate a
  fix and disclosure timeline. If a CodeQL alert appears exploitable, include a
  PoC via the advisory channel.

# Security Posture: Jobs Paths and Artifacts

This service handles user-provided identifiers (e.g., `job_id`) and file names
to locate artifacts on disk. We implement strict validation and containment to
prevent path traversal and symlink escape.

## Key defenses

- Single-segment allowlists: `job_id` and `file` must match conservative regexes
  and equal their basename; separators and traversal tokens are rejected.
- Containment checks: all joins use `os.path.normpath` and `os.path.commonpath`
  to ensure computed paths remain under the configured base directory.
- Symlink rejection: file access uses `os.open(..., O_NOFOLLOW)`; `ELOOP` is
  treated as an invalid parameter. This prevents symlink-based escapes.
- Descriptor-based stats: TTL and metadata rely on `os.fstat()` on an open file
  descriptor, avoiding path-based `stat()` on tainted inputs.
- No directory iteration over tainted prefixes: default selection leverages
  recorded output or a generated manifest to avoid listing arbitrary paths in
  request handlers.

About CodeQL “Uncontrolled data used in path expression”

The default query is conservative and may not model the above sanitizers.
Where necessary, we suppress with `# lgtm [py/path-injection]` on lines that use
contained, validated paths (e.g., `os.open` with `O_NOFOLLOW`, `open(mf)` after
`commonpath` checks). Suppressions are limited and justified in-line.

## Operational guidance

- Configure `ZYRA_RESULTS_DIR` to a dedicated directory owned by the
  service. Do not point it at shared or sensitive system paths.
- Do not relax allowlists without revisiting containment and tests.
- Keep tests for traversal and TTL behavior green.

