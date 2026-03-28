from __future__ import annotations

from alembic import op

from app.core.db import Base
from app.domain import models  # noqa: F401

revision = "20260328_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
