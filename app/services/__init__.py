"""Services layer for PKM system.

Provides business logic services for entries, search, tags, snapshots,
and attachments. Each service takes an AsyncSession and encapsulates
all database operations for its domain.
"""

from __future__ import annotations
