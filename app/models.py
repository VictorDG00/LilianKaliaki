# Modelos SQLModel (Servico, Contato, Reserva, Produto, Pedido)

from datetime import datetime, time
from typing import Optional, List
from enum import Enum
from sqlmodel import SQLModel, Field, Relationship

class Servico(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    titulo: str
    descricao: Optional[str] = None
    duracao_min: int
    preco: float
    ativo: bool = Field(default=True)
    # lazy=selectin e obrigatorio no SQLAlchemy async: sem isso, ler .fotos
    # fora da sessao estoura MissingGreenlet na listagem do admin.
    fotos: List["Foto"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "order_by": "Foto.ordem",
            "cascade": "all, delete-orphan",
        }
    )

class Disponibilidade(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    dia_semana: int
    hora_inicio: time
    hora_fim: time

class Contato(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    email: str = Field(index=True)
    telefone: str
    consentimento_marketing: bool = Field(default=False)
    criado_em: datetime = Field(default_factory=datetime.utcnow)

class StatusReserva(str, Enum):
    PENDENTE = "Pendente"
    CONFIRMADA = "Confirmada"
    EXPIRADA = "Expirada"
    CANCELADA = "Cancelada"

class Reserva(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    servico_id: int = Field(foreign_key="servico.id")
    contato_id: int = Field(foreign_key="contato.id")
    data_hora: datetime = Field(index=True)
    status: StatusReserva = Field(default=StatusReserva.PENDENTE)
    expira_em: datetime
    mp_payment_id: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Produto(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    titulo: str
    descricao: Optional[str] = None
    preco: float
    ativo: bool = Field(default=True)
    fotos: List["Foto"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "order_by": "Foto.ordem",
            "cascade": "all, delete-orphan",
        }
    )


MAX_FOTOS = 4


class Foto(SQLModel, table=True):
    """Imagem de um servico OU de um produto — uma das duas FKs, nunca as duas.

    Uma tabela para os dois donos em vez de foto1..foto4 em cada um: o limite de
    MAX_FOTOS e regra de negocio (validada em app/fotos.py), nao de schema.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    servico_id: Optional[int] = Field(default=None, foreign_key="servico.id", index=True)
    produto_id: Optional[int] = Field(default=None, foreign_key="produto.id", index=True)
    arquivo: str  # caminho relativo dentro de media/, ja convertido para .webp
    ordem: int = Field(default=0)
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class StatusPedido(str, Enum):
    PENDENTE = "Pendente"
    CONFIRMADO = "Confirmado"
    CANCELADO = "Cancelado"


class Pedido(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    produto_id: int = Field(foreign_key="produto.id")
    contato_id: int = Field(foreign_key="contato.id")
    status: StatusPedido = Field(default=StatusPedido.PENDENTE)
    mp_payment_id: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class Post(SQLModel, table=True):
    """Conteudo editorial. NAO vende: sem preco, sem status de pedido.

    E a diferenca estrutural em relacao ao Produto, e o que impede o blog de
    virar caminho de compra por acidente (guardrail 1 da sprint_0.4).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    titulo: str
    slug: str = Field(index=True, unique=True)
    resumo: Optional[str] = None  # card na home + meta description
    conteudo: str  # texto puro; quebras de linha preservadas no CSS
    imagem_url: Optional[str] = None  # link externo, sem upload
    publicado: bool = Field(default=False)  # rascunho nao aparece em lugar nenhum
    publicado_em: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)