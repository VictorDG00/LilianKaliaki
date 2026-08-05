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