# SPDX-License-Identifier: Apache-2.0
"""Registry for interactive renderers."""

from __future__ import annotations

from typing import Iterable, TypeVar

from .base import InteractiveRenderer

_RendererT = TypeVar("_RendererT", bound=InteractiveRenderer)

_REGISTRY: dict[str, type[InteractiveRenderer]] = {}


def register(renderer_cls: type[_RendererT]) -> type[_RendererT]:
    """Register ``renderer_cls`` keyed by its ``slug`` attribute."""

    if not issubclass(renderer_cls, InteractiveRenderer):
        raise TypeError("renderer must inherit InteractiveRenderer")
    slug = renderer_cls.slug
    if not slug:
        raise ValueError("renderer slug must be non-empty")
    if slug in _REGISTRY:
        raise ValueError(f"renderer slug already registered: {slug}")
    _REGISTRY[slug] = renderer_cls
    return renderer_cls


def get(slug: str) -> type[InteractiveRenderer]:
    """Return the renderer class registered for ``slug``."""

    try:
        return _REGISTRY[slug]
    except KeyError as exc:
        raise KeyError(f"unknown renderer slug: {slug}") from exc


def create(slug: str, **options) -> InteractiveRenderer:
    """Instantiate the renderer registered under ``slug``."""

    cls = get(slug)
    return cls(**options)


def available() -> Iterable[type[InteractiveRenderer]]:
    """Yield all registered renderer classes."""

    return _REGISTRY.values()
