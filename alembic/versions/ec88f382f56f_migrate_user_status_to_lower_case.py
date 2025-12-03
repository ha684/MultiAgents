"""migrate user status to lower case

Revision ID: ec88f382f56f
Revises: b896907133a9
Create Date: 2025-12-03 09:45:54.401685

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec88f382f56f"
down_revision: Union[str, Sequence[str], None] = "b896907133a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute(
        "CREATE TYPE userstatus_new AS ENUM ('active', 'inactive', 'suspended', 'pending_verification')"
    )

    op.execute("""
        ALTER TABLE users
        ALTER COLUMN status TYPE userstatus_new
        USING (LOWER(status::text)::userstatus_new)
    """)

    op.execute("DROP TYPE userstatus")

    op.execute("ALTER TYPE userstatus_new RENAME TO userstatus")


def downgrade():
    op.execute(
        "CREATE TYPE userstatus_new AS ENUM ('ACTIVE', 'INACTIVE', 'SUSPENDED', 'PENDING_VERIFICATION')"
    )

    op.execute("""
        ALTER TABLE users
        ALTER COLUMN status TYPE userstatus_new
        USING (UPPER(status::text)::userstatus_new)
    """)

    op.execute("DROP TYPE userstatus")

    op.execute("ALTER TYPE userstatus_new RENAME TO userstatus")
