"""Prompt-2A storage and multi-session core.

This package is deliberately independent from Fiji.  It implements only the
approved schema-v2 storage, source identity, session pointer and explicit
revision-clone boundary.  Migration, archive/restore and GUI integration are
outside this package.
"""

from .session_core import (
    CURRENT_REVISION_HEADER,
    CURRENT_RUN_HEADER,
    CURRENT_SESSION_HEADER,
    SESSION_REGISTRY_HEADER,
    CloneResult,
    ImageBinding,
    ProjectValidation,
    PublishedRevision,
    PublishedRun,
    SelectionResult,
    SessionCore,
    SessionRecord,
    create_project,
    sha256_file,
    snapshot_tree,
    validate_project,
    verify_approved_contract,
)

__all__ = [
    "CURRENT_REVISION_HEADER",
    "CURRENT_RUN_HEADER",
    "CURRENT_SESSION_HEADER",
    "SESSION_REGISTRY_HEADER",
    "CloneResult",
    "ImageBinding",
    "ProjectValidation",
    "PublishedRevision",
    "PublishedRun",
    "SelectionResult",
    "SessionCore",
    "SessionRecord",
    "create_project",
    "sha256_file",
    "snapshot_tree",
    "validate_project",
    "verify_approved_contract",
]
