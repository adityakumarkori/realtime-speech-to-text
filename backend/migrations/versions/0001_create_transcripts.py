"""Create transcripts table.

Revision ID: 0001
Revises:
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(length=35), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_transcripts_session_sequence",
        ),
        sa.CheckConstraint(
            "sequence >= 0",
            name="ck_transcripts_sequence_non_negative",
        ),
        sa.CheckConstraint(
            "length(trim(text)) > 0",
            name="ck_transcripts_text_not_blank",
        ),
    )
    op.create_index(
        "ix_transcripts_session_created_at",
        "transcripts",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transcripts_session_created_at",
        table_name="transcripts",
    )
    op.drop_table("transcripts")
