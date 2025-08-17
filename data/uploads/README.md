This directory is used for runtime uploads and temporary files.

- Purpose: the API and examples write uploaded or transient files here.
- Versioning: the folder is kept in Git via the `.gitkeep` placeholder; do not commit uploaded data.
- Hygiene: avoid storing sensitive data; files may be cleared between runs.

