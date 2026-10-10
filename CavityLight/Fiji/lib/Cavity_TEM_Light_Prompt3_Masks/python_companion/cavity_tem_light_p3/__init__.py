"""Prompt-3 mask visibility, geometry-cache and Fiji integration layer.

This package is an additive technical-preview adapter.  Prompt-2 remains the
session/revision/RUN authority; Prompt-3 adds a distinct scientific-geometry
domain plus operational display and cache state.
"""

from .mask_visibility import (
    AREA_CACHE_SCHEMA,
    DISPLAY_PREFERENCES_SCHEMA,
    GEOMETRY_CACHE_SCHEMA,
    prepare_geometry_state,
    set_display_mode,
)

__all__ = [
    "AREA_CACHE_SCHEMA",
    "DISPLAY_PREFERENCES_SCHEMA",
    "GEOMETRY_CACHE_SCHEMA",
    "prepare_geometry_state",
    "set_display_mode",
]
