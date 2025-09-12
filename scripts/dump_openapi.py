#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from zyra.api.server import app


def main() -> int:
    spec = app.openapi()
    print(json.dumps(spec, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
