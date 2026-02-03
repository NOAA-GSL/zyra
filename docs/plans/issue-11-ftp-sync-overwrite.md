# Implementation Plan: FTP Sync Overwrite Modes and Metadata-Aware Sync

**Issue:** [#11 - `acquire ftp`: add overwrite mode and metadata-aware sync for filled-frame use cases](https://github.com/zyra-project/zyra/issues/11)

**Branch:** `claude/github-issue-11-EESdo`

---

## Problem Statement

The `acquire ftp --sync-dir` feature prevents re-downloading existing files. However, when upstream FTP servers backfill missing data with real information (replacing interpolated/placeholder frames), the stale local data persists because filenames remain unchanged.

---

## Key Files to Modify

| File | Purpose |
|------|---------|
| `src/zyra/connectors/backends/ftp.py` | Core sync logic, add `SyncOptions` dataclass and decision function |
| `src/zyra/connectors/ingest/__init__.py` | CLI argument registration and handler |
| `src/zyra/api/schemas/domain_args.py` | API schema updates |
| `src/zyra/connectors/clients.py` | Update `FTPConnector.sync_directory()` signature |
| `tests/connectors/test_ftp_backend.py` | Unit tests for new functionality |

---

## Architecture Decisions

### 1. New `SyncOptions` Dataclass

A frozen dataclass to encapsulate all sync behavior configuration, following existing patterns in the codebase:

```python
@dataclass(frozen=True)
class SyncOptions:
    """Configuration for FTP sync file replacement behavior."""
    overwrite_existing: bool = False
    recheck_existing: bool = False
    min_remote_size: int | str | None = None  # bytes or percentage like "10%"
    prefer_remote: bool = False
    prefer_remote_if_meta_newer: bool = False
    skip_if_local_done: bool = False
    recheck_missing_meta: bool = False
    frames_meta_path: str | None = None
```

### 2. New `should_download()` Function

Central decision logic implementing this precedence order:

1. `--skip-if-local-done`: Check for `.done` marker file first
2. File doesn't exist locally → always download
3. Zero-byte local file → always replace
4. `--overwrite-existing`: Unconditional download
5. `--prefer-remote`: Always download
6. `--prefer-remote-if-meta-newer`: Check `frames-meta.json` timestamps
7. `--recheck-missing-meta`: Download if companion metadata missing
8. `--min-remote-size`: Size-based comparison
9. `--recheck-existing`: Size comparison when mtime unavailable
10. **Default**: MDTM-based timestamp comparison

### 3. New `get_remote_mtime()` Function

Uses FTP's `MDTM` command to get file modification time (fails gracefully when unsupported).

---

## Implementation Phases

### Phase 1: Core Backend (`ftp.py`)

1. Add `SyncOptions` dataclass
2. Implement `get_remote_mtime()` function
3. Implement helper functions:
   - `_parse_min_size()` - Parse bytes or percentage size spec
   - `_load_frames_meta()` - Load frames-meta.json file
   - `_has_done_marker()` - Check for .done marker file
   - `_is_missing_companion_meta()` - Check if file is missing from metadata
4. Implement `should_download()` logic
5. Update `sync_directory()` signature and loop
6. Write unit tests for new functions

### Phase 2: CLI Integration (`ingest/__init__.py`)

1. Add new CLI arguments to FTP parser
2. Update `_cmd_ftp()` to construct `SyncOptions`
3. Pass options to `sync_directory()`
4. Write CLI integration tests

### Phase 3: API Schema (`domain_args.py`)

1. Update `AcquireFtpArgs` model with new fields
2. Update `normalize_and_validate()` if needed
3. Test API endpoint with new parameters

### Phase 4: Connector Client (`clients.py`)

1. Update `FTPConnector.sync_directory()` signature
2. Pass through `sync_options` parameter

### Phase 5: Documentation and Cleanup

1. Update CLI help strings
2. Add docstrings with examples
3. Update any sample workflows using FTP sync

---

## New CLI Flags

| Flag | Type | Description |
|------|------|-------------|
| `--overwrite-existing` | bool | Unconditional replacement regardless of timestamps |
| `--recheck-existing` | bool | Compare file sizes when timestamps unavailable |
| `--min-remote-size` | str/int | Replace if remote larger (bytes or "10%") |
| `--prefer-remote` | bool | Always prioritize remote versions |
| `--prefer-remote-if-meta-newer` | bool | Use frames-meta.json timestamps |
| `--skip-if-local-done` | bool | Respect .done marker files |
| `--recheck-missing-meta` | bool | Re-download files lacking metadata |
| `--frames-meta` | path | Path to frames-meta.json |

---

## Potential Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| MDTM not supported by all servers | Medium | Graceful fallback with logging; document behavior |
| Performance from extra MDTM calls | High | Cache connection; batch metadata queries |
| frames-meta.json format changes | Low | Validate JSON structure; log warnings |
| Timezone handling in MDTM | Medium | Document UTC assumption |

---

## Test Strategy

### Unit Tests (`test_ftp_backend.py`)

- `test_get_remote_mtime_success` - MDTM parsing when server supports it
- `test_get_remote_mtime_not_supported` - Graceful handling when unsupported
- `test_parse_min_size_bytes` - Parsing absolute byte values
- `test_parse_min_size_percentage` - Parsing percentage values
- `test_should_download_*` - All decision logic branches
- `test_sync_directory_with_sync_options` - Integration test

### CLI Tests

- Verify new arguments are recognized
- Test argument combinations

---

## Usage Examples

```bash
# Default: use MDTM timestamps
zyra acquire ftp ftp://server/data/ --sync-dir ./local/

# Force overwrite all files
zyra acquire ftp ftp://server/data/ --sync-dir ./local/ --overwrite-existing

# Only replace if remote is significantly larger
zyra acquire ftp ftp://server/data/ --sync-dir ./local/ --min-remote-size "20%"

# Use metadata-aware sync
zyra acquire ftp ftp://server/frames/ --sync-dir ./frames/ \
    --frames-meta ./frames-meta.json \
    --prefer-remote-if-meta-newer

# Skip completed files
zyra acquire ftp ftp://server/data/ --sync-dir ./local/ --skip-if-local-done
```

---

*Ready for implementation upon approval.*
