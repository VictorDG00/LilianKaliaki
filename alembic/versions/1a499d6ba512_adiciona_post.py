"""adiciona post

Revision ID: 1a499d6ba512
Revises: 9e1d477ab709
Create Date: 2026-08-06 03:13:27.543517

Revisao manual do autogenerate (regra do CLAUDE.md secao 3):

1. O autogenerate quis DROPAR o indice 'unique_reserva_ativa' — ele nao enxerga
   indices parciais criados a mao e os trata como "removidos do metadata".
   Esse indice e a trava final contra reserva dupla; o drop foi removido daqui.
2. Faltava o `import sqlmodel`, usado pelo AutoString das colunas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '1a499d6ba512'
down_revision: Union[str, Sequence[str], None] = '9e1d477ab709'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'post',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('titulo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('resumo', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('conteudo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('imagem_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('publicado', sa.Boolean(), nullable=False),
        sa.Column('publicado_em', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_post_slug'), 'post', ['slug'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_post_slug'), table_name='post')
    op.drop_table('post')
