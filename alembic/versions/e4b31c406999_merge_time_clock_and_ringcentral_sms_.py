"""merge time clock and ringcentral sms heads

Revision ID: e4b31c406999
Revises: 1745e318c65a, fc6450e398ee
Create Date: 2026-10-04 01:28:08.503862
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4b31c406999'
down_revision: Union[str, None] = ('1745e318c65a', 'fc6450e398ee')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
