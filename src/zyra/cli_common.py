"""Shared CLI helpers and common options.

This module can hold reusable option builders as the CLI grows.
"""

from __future__ import annotations

import argparse


def add_output_option(p: argparse.ArgumentParser, *, default: str = "-") -> None:
    p.add_argument(
        "-o", "--output", default=default, help="Output path or '-' for stdout"
    )


def add_input_option(p: argparse.ArgumentParser, *, required: bool = False) -> None:
    p.add_argument(
        "-i", "--input", required=required, help="Input path or '-' for stdin"
    )
