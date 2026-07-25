# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import contextlib
import re
import tempfile
from typing import Callable, Iterable, Iterator

from .io_utils import open_input  # re-export


def read_all_bytes(path_or_dash: str) -> bytes:
    """Read all bytes from a path or '-' (stdin)."""
    with open_input(path_or_dash) as f:
        return f.read()


def is_netcdf_bytes(b: bytes) -> bool:
    """Return True if bytes look like NetCDF (classic CDF or HDF5-based).

    Recognizes magic headers:
    - Classic NetCDF: ``b"CDF"``
    - NetCDF4/HDF5:  ``b"\x89HDF"``
    """
    return b.startswith(b"CDF") or b.startswith(b"\x89HDF")


def is_grib2_bytes(b: bytes) -> bool:
    """Return True if bytes look like GRIB (``b"GRIB"``)."""
    return b.startswith(b"GRIB")


def detect_format_bytes(b: bytes) -> str:
    """Detect basic format from magic bytes.

    Returns one of: ``"netcdf"``, ``"grib2"``, or ``"unknown"``.
    """
    if is_netcdf_bytes(b):
        return "netcdf"
    if is_grib2_bytes(b):
        return "grib2"
    return "unknown"


@contextlib.contextmanager
def temp_file_from_bytes(data: bytes, *, suffix: str = "") -> Iterator[str]:
    """Write bytes to a NamedTemporaryFile and yield its path; delete on exit."""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()
        yield tmp.name
    finally:
        from contextlib import suppress
        from pathlib import Path

        with suppress(Exception):
            Path(tmp.name).unlink()


def parse_levels_arg(val) -> int | list[float]:
    """Parse levels from int or comma-separated floats."""
    if isinstance(val, int):
        return val
    if isinstance(val, (list, tuple)):
        return [float(x) for x in val]
    s = str(val)
    try:
        return int(s)
    except ValueError:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return [float(p) for p in parts]


def configure_logging_from_env(default: str = "info") -> None:
    """Set logging levels based on VERBOSITY env (supports ZYRA_*/DATAVIZHUB_*).

    Values: debug|info|quiet. Defaults to 'info'.
    - debug: root=DEBUG
    - info: root=INFO
    - quiet: root=ERROR (suppress most logs)
    Also dials down noisy third-party loggers (matplotlib, cartopy, botocore, requests).
    """
    import logging

    level_map = {"debug": logging.DEBUG, "info": logging.INFO, "quiet": logging.ERROR}
    from zyra.utils.env import env

    verb = (env("VERBOSITY", default) or default).lower()
    level = level_map.get(verb, logging.INFO)

    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    for name in ("matplotlib", "cartopy", "botocore", "urllib3", "requests"):
        with contextlib.suppress(Exception):
            logging.getLogger(name).setLevel(
                max(level, logging.WARNING) if verb != "debug" else level
            )


def sanitize_for_log(text: str) -> str:
    """Redact secrets in URLs/headers for safe logging.

    - Redacts user:pass in URLs (scheme://user:pass@host)
    - Redacts common token/secret query params (token, signature, X-Amz-*, apikey, key, secret, password)
    - Redacts Authorization: Bearer tokens
    """
    s = str(text)
    # user:pass@
    s = re.sub(r"(://[^/@:]+:)[^@]+(@)", r"\1***\2", s)
    # Query parameters with sensitive names (case-insensitive)
    s = re.sub(
        r"(?i)([?&])(token|access_token|refresh_token|authorization_code|signature|sig|x-amz-signature|x-amz-credential|x-amz-security-token|apikey|api_key|access_key|client_secret|secret|password)=([^&#\s]+)",
        r"\1\2=***",
        s,
    )
    # Authorization headers
    s = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s]+", r"\1***", s)
    return s


def sanitize_args(args: Iterable[str]) -> list[str]:
    """Return a sanitized copy of a command arg vector for logging."""
    return [sanitize_for_log(a) for a in list(args)]


def resolve_batch_output_names(
    inputs: list[str],
    output_names: list[str] | None,
    *,
    derive: Callable[[str], str],
) -> list[str]:
    """Resolve destination filenames for a batch stage.

    Batch commands name outputs after their input by default, which keeps
    a chain of batch stages aligned without the caller restating every
    filename. That also means an output's identity is fixed by whatever
    the source happened to be called — fine for a one-shot conversion,
    wrong for frames whose name has to carry a valid time.

    ``output_names`` overrides the derived names positionally.

    Raises
    ------
    ValueError
        If the two lists differ in length, or two entries would resolve
        to the same destination. Handlers surface these as exit code 2.
    """
    explicit = output_names is not None
    if not explicit:
        names = [derive(src) for src in inputs]
    else:
        if len(output_names) != len(inputs):
            raise ValueError(
                f"--output-names must have one entry per --inputs "
                f"({len(output_names)} names for {len(inputs)} inputs)"
            )
        names = list(output_names)
    seen: dict[str, str] = {}
    for name, src in zip(names, inputs):
        prior = seen.get(name)
        if prior is not None:
            # Two different failures wearing the same shape: derived names
            # collide because the sources happen to share a basename (the
            # caller may not even realize it), while explicit names collide
            # because the caller typed one twice. Say which.
            if explicit:
                raise ValueError(
                    f"--output-names repeats {name!r} "
                    f"(for inputs {prior} and {src})"
                )
            raise ValueError(
                f"--inputs collide on output {name}: {prior} and {src} share a filename"
            )
        seen[name] = src
    return names
