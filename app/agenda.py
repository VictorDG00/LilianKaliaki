# Regras da agenda: o que esta aberto, o que esta bloqueado e o que sobra.
#
# Mora aqui, e nao na rota, porque duas telas perguntam a mesma coisa — o site
# publico ("que horario tem?") e o painel ("esse intervalo faz sentido?").

from datetime import date, datetime, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Ausencia, Disponibilidade, Reserva, RESERVA_ATIVA, Servico

# Ordem de exibicao pedida (Domingo a Sabado) sobre o weekday do Python, onde
# 0 = segunda e 6 = domingo.
DIAS_DA_SEMANA = [
    (6, "Domingo"),
    (0, "Segunda"),
    (1, "Terça"),
    (2, "Quarta"),
    (3, "Quinta"),
    (4, "Sexta"),
    (5, "Sábado"),
]


async def ausencia_na_data(session: AsyncSession, dia: date) -> Ausencia | None:
    """A ausencia que cobre esse dia, se houver. Intervalo fechado nas pontas."""
    return (
        await session.exec(
            select(Ausencia).where(Ausencia.data_inicio <= dia, Ausencia.data_fim >= dia)
        )
    ).first()


def erro_nos_intervalos(intervalos: list[tuple]) -> str | None:
    """Valida os intervalos de UM dia. Devolve a mensagem, ou None se esta ok.

    Duas regras: fim depois do inicio, e nenhum intervalo por cima do outro —
    senao o mesmo horario apareceria duas vezes para o cliente.
    """
    for inicio, fim in intervalos:
        if fim <= inicio:
            return "O fim precisa ser depois do início."

    em_ordem = sorted(intervalos)
    for (_, fim_anterior), (inicio, _) in zip(em_ordem, em_ordem[1:]):
        if inicio < fim_anterior:
            return "Há horários se sobrepondo no mesmo dia."
    return None


async def horarios_livres(
    session: AsyncSession, servico: Servico, dia: date, agora: datetime | None = None
) -> list[datetime]:
    """Horarios que o cliente pode escolher, na ordem da regra de negocio:

    1. dia dentro de uma ausencia -> nada;
    2. intervalos ativos daquele dia da semana (dia sem intervalo -> nada);
    3. fatia pela duracao do servico;
    4. desconta as reservas ativas;
    5. descarta o que ja passou.
    """
    if await ausencia_na_data(session, dia) is not None:
        return []

    intervalos = (
        await session.exec(
            select(Disponibilidade).where(
                Disponibilidade.dia_semana == dia.weekday(),
                Disponibilidade.ativo == True,  # noqa: E712
            )
        )
    ).all()
    if not intervalos:
        return []

    duracao = timedelta(minutes=servico.duracao_min)
    candidatos = []
    for intervalo in intervalos:
        slot = datetime.combine(dia, intervalo.hora_inicio)
        fim = datetime.combine(dia, intervalo.hora_fim)
        while slot + duracao <= fim:
            candidatos.append(slot)
            slot += duracao

    inicio_do_dia = datetime.combine(dia, datetime.min.time())
    ocupados = set(
        (
            await session.exec(
                select(Reserva.data_hora).where(
                    Reserva.servico_id == servico.id,
                    Reserva.status.in_(RESERVA_ATIVA),
                    Reserva.data_hora >= inicio_do_dia,
                    Reserva.data_hora < inicio_do_dia + timedelta(days=1),
                )
            )
        ).all()
    )

    # Hora local, nao UTC: os intervalos sao hora de parede do negocio, e
    # datetime.utcnow() escondia as proximas 3h de horarios do mesmo dia.
    agora = agora or datetime.now()
    return sorted(s for s in candidatos if s not in ocupados and s >= agora)
