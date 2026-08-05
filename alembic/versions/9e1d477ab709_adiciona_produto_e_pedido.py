"""adiciona produto e pedido

Revision ID: 9e1d477ab709
Revises: 2e4fae625fbf
Create Date: 2026-08-05 17:44:13.708452

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '9e1d477ab709'
down_revision: Union[str, Sequence[str], None] = '2e4fae625fbf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('produto',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('titulo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('descricao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('preco', sa.Float(), nullable=False),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pedido',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('produto_id', sa.Integer(), nullable=False),
    sa.Column('contato_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('PENDENTE', 'CONFIRMADO', 'CANCELADO', name='statuspedido'), nullable=False),
    sa.Column('mp_payment_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['contato_id'], ['contato.id'], ),
    sa.ForeignKeyConstraint(['produto_id'], ['produto.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # rename, nao drop+add: preserva dados existentes de contato.
    # (autogenerate nao detecta renomeacoes e nao enxerga o indice unico
    # parcial, que vive so na migration anterior, nao no metadata do
    # SQLModel - por isso NAO incluimos aqui o drop_index que ele gerou
    # sozinho pra 'unique_reserva_ativa'.)
    # condicional: bancos criados a partir da migration ja corrigida
    # (ex.: db_test recem-criado) nunca tiveram a coluna com o typo.
    colunas = [c["name"] for c in sa.inspect(op.get_bind()).get_columns("contato")]
    if "consentiment_markegin" in colunas:
        op.alter_column("contato", "consentiment_markegin", new_column_name="consentimento_marketing")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('contato', 'consentimento_marketing', new_column_name='consentiment_markegin')
    op.drop_table('pedido')
    op.drop_table('produto')
