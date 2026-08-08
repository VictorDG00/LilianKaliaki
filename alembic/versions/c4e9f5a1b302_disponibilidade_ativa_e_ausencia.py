"""dia da semana liga/desliga e periodos de ausencia

Revision ID: c4e9f5a1b302
Revises: b7c1a2d40f11
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "c4e9f5a1b302"
down_revision: Union[str, Sequence[str], None] = "b7c1a2d40f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default: as linhas que ja existem continuam valendo (o horario
    # cadastrado hoje nao pode sumir da agenda por causa da migration).
    op.add_column(
        "disponibilidade",
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "ausencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=False),
        sa.Column("motivo", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint("data_fim >= data_inicio", name="ck_ausencia_periodo"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ausencia_data_inicio", "ausencia", ["data_inicio"])
    op.create_index("ix_ausencia_data_fim", "ausencia", ["data_fim"])


def downgrade() -> None:
    op.drop_index("ix_ausencia_data_fim", table_name="ausencia")
    op.drop_index("ix_ausencia_data_inicio", table_name="ausencia")
    op.drop_table("ausencia")
    op.drop_column("disponibilidade", "ativo")
