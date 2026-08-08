"""adiciona foto de servico e produto

Revision ID: b7c1a2d40f11
Revises: 1a499d6ba512
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "b7c1a2d40f11"
down_revision: Union[str, Sequence[str], None] = "1a499d6ba512"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "foto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("servico_id", sa.Integer(), nullable=True),
        sa.Column("produto_id", sa.Integer(), nullable=True),
        sa.Column("arquivo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["servico_id"], ["servico.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["produto_id"], ["produto.id"], ondelete="CASCADE"),
        # Uma foto pertence a um servico OU a um produto, nunca aos dois nem a
        # nenhum — a trava no banco evita linha orfa por bug de rota.
        sa.CheckConstraint(
            "(servico_id IS NOT NULL) <> (produto_id IS NOT NULL)",
            name="ck_foto_um_dono_so",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_foto_servico_id", "foto", ["servico_id"])
    op.create_index("ix_foto_produto_id", "foto", ["produto_id"])


def downgrade() -> None:
    op.drop_index("ix_foto_produto_id", table_name="foto")
    op.drop_index("ix_foto_servico_id", table_name="foto")
    op.drop_table("foto")
