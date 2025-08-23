This plan ensures all legacy functionality from `acquisition/` is migrated into the new `connectors/` (and `utils/` where appropriate).  
Once complete, the old **`rtvideo.py` workflow** will be fully reproducible in declarative pipelines.

---

## 1. FTP (`acquisition/ftp_manager.py`)

### Current (legacy)
- `sync_ftp_directory(remote_dir, local_dir, dataset_period)`  
  - Lists remote files  
  - Filters by regex/date range  
  - Downloads missing files  
  - Cleans zero-byte files  

### Migration
- **Connector API (`connectors/backends/ftp.py`):**
  - `list_files(remote_dir, pattern=None, since=None, until=None)`  
  - `sync_directory(remote_dir, local_dir, pattern=None, since=None, until=None)`  
  - `delete(path)`, `exists(path)`, `stat(path)`  
- **Pipeline Support:**  
  - YAML config example:
    ```yaml
    since: "2024-08-01"
    until: "2025-08-01"
    file_pattern: "image_(\d{8})\.png"
    date_format: "%Y%m%d"
    ```

Restores `rtvideo.py` “last year’s files” functionality.

---

## 2. HTTP (`acquisition/http_manager.py`)

### Current (legacy)
- Fetch binary/text/JSON (`fetch_data`, `fetch_text`, `fetch_json`)  
- POST data (`post_data`)  
- `list_files(url, pattern)` — scrape directory listings  
- `.idx` handling (parse lines, derive byte ranges, ranged downloads)

### Migration
- **Connector (`connectors/backends/http.py`):**  
  - `fetch_bytes(url)`  
  - `fetch_text(url)`  
  - `fetch_json(url)`  
  - `post_data(url, data, headers)`  
  - `list_files(url, pattern)` (optional)  
- **Utils (`utils/grib.py`):**  
  - `.idx` parsing + byte range helpers  
  - parallel downloads  

---

## 3. S3 (`acquisition/s3_manager.py`)

### Current (legacy)
- `list_files(prefix, pattern)`  
- `fetch`, `upload`, `exists`, `delete`, `stat`  
- `.idx` parsing, ranged downloads  

### Migration
- **Connector (`connectors/backends/s3.py`):**  
  - `list_files(prefix=None, pattern=None, since=None, until=None)`  
  - `exists(key)`, `delete(key)`, `stat(key)`  
- **Utils (`utils/grib.py`):**  
  - `.idx` parsing + ranged downloads  

---

## 4. Vimeo (`acquisition/vimeo_manager.py`)

### Current (legacy)
- `upload_video(file)`  
- `update_video(file, video_uri)`  
- `update_video_description(video_uri, new_description)`  
- No fetch/list  

### Migration
- **Connector (`connectors/backends/vimeo.py`):**  
  - `upload_bytes(path)`  
  - `update_video(path, video_uri)`  
  - `update_description(video_uri, text)`  

Treat Vimeo as **upload-only sink connector**.

---

## 5. GRIB Utils (`acquisition/grib_utils.py`)

### Current (legacy)
- `.idx` helpers  
- Byte range utilities  
- Parallel downloads  

### Migration
- **Move entirely to `utils/grib.py`**  
- Imported by FTP/HTTP/S3 connectors when needed.  

---

## 6. Pipeline & CLI Enhancements

- Add support for `since`, `until`, `file_pattern`, `date_format` in YAML configs.  
- Add `transform` stage type for structured metadata (e.g. start/end dates → JSON).  
- CLI support example:
  ```bash
  zyra run pipeline.yaml --set fetch_images.since=2024-08-01
  ```

---

## 7. Removal of `acquisition/`

- Once all functionality above is ported:  
  - Update imports to use `connectors/` and `utils/`  
  - Update pipelines with new connector features  
  - Remove `acquisition/` directory completely  
  - Add tests to ensure no regressions from old scripts (`rtvideo.py`)  

---

## Outcome

- **`rtvideo.py` workflow replicated in pipelines:**  
  - FTP sync by date range  
  - ffmpeg movie composition  
  - Vimeo update/replace upload  
  - S3 metadata upload  

- **All `acquisition/` functionality migrated or retired**  
- **Pipelines fully declarative, reproducible, and testable**
