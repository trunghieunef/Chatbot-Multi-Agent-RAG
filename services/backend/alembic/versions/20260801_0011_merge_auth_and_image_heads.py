"""merge auth/chat and article/project image migration heads

Revision ID: 20260801_0011
Revises: 20260603_0011, 20260801_0010
Create Date: 2026-08-01 00:11:00
"""

from typing import Sequence, Union


revision: str = "20260801_0011"
down_revision: Union[str, tuple[str, str], None] = ("20260603_0011", "20260801_0010")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
