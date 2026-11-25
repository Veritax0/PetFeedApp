from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from comedero.configuracion import configuracion
from comedero.excepciones import DatosInvalidos
from comedero.modelos import (
    Comedero,
    ComederoMascota,
    EventoRfid,
    LecturaPeso,
    SesionComida,
    TagRfid,
)

ManejadorMensaje = Callable[[Session, str, dict, datetime], None]


def obtenerOCrearComedero(
    sesionBd: Session, comederoId: str, ahora: datetime
) -> tuple[Comedero, bool]:
    comedero = sesionBd.get(Comedero, comederoId)
    esNuevo = comedero is None
    if comedero is None:
        comedero = Comedero(id=comederoId)
        sesionBd.add(comedero)
    comedero.ultimaConexion = ahora
    return comedero, esNuevo


def cerrarSesionesVencidas(
    sesionBd: Session, ahora: datetime, comederoId: str | None = None
) -> None:
    limiteInactividad = ahora - timedelta(seconds=configuracion.segundosInactividadSesion)
    consulta = select(SesionComida).where(
        SesionComida.fin.is_(None), SesionComida.ultimaDeteccion < limiteInactividad
    )
    if comederoId is not None:
        consulta = consulta.where(SesionComida.comederoId == comederoId)
    for sesionVencida in sesionBd.scalars(consulta).all():
        sesionVencida.fin = sesionVencida.ultimaDeteccion


def obtenerSesionAbierta(sesionBd: Session, comederoId: str) -> SesionComida | None:
    consulta = (
        select(SesionComida)
        .where(SesionComida.comederoId == comederoId, SesionComida.fin.is_(None))
        .order_by(SesionComida.inicio.desc())
    )
    return sesionBd.scalars(consulta).first()


def procesarTelemetria(
    sesionBd: Session, comederoId: str, datos: dict, ahora: datetime
) -> None:
    pesoCrudo = datos.get("peso_crudo")
    if pesoCrudo is None:
        return
    cerrarSesionesVencidas(sesionBd, ahora, comederoId)
    sesionAbierta = obtenerSesionAbierta(sesionBd, comederoId)
    sesionBd.add(
        LecturaPeso(
            comederoId=comederoId,
            mascotaId=sesionAbierta.mascotaId if sesionAbierta else None,
            sesionId=sesionAbierta.id if sesionAbierta else None,
            fecha=ahora,
            pesoCrudo=int(pesoCrudo),
        )
    )


def procesarEventoTag(
    sesionBd: Session, comederoId: str, datos: dict, ahora: datetime
) -> None:
    tagHexRecibido = datos.get("hex")
    if not isinstance(tagHexRecibido, str):
        raise DatosInvalidos("El evento de tag no incluye el campo hex")
    tagHex = tagHexRecibido.upper()
    cerrarSesionesVencidas(sesionBd, ahora, comederoId)
    tag = sesionBd.scalars(select(TagRfid).where(TagRfid.tagHex == tagHex)).first()
    mascotaId = tag.mascotaId if tag is not None else None
    estaAutorizado = (
        tag is not None
        and tag.activo
        and sesionBd.get(ComederoMascota, (comederoId, tag.mascotaId)) is not None
    )
    sesionAbierta = obtenerSesionAbierta(sesionBd, comederoId)
    if estaAutorizado and sesionAbierta is not None and sesionAbierta.mascotaId == mascotaId:
        sesionAbierta.ultimaDeteccion = ahora
        return
    sesionBd.add(
        EventoRfid(
            comederoId=comederoId,
            fecha=ahora,
            tagHex=tagHex,
            mascotaId=mascotaId,
            autorizado=estaAutorizado,
        )
    )
    if estaAutorizado:
        if sesionAbierta is not None:
            sesionAbierta.fin = sesionAbierta.ultimaDeteccion
        sesionBd.add(
            SesionComida(
                comederoId=comederoId,
                mascotaId=mascotaId,
                inicio=ahora,
                ultimaDeteccion=ahora,
            )
        )


manejadoresPorTipoMensaje: dict[str, ManejadorMensaje] = {
    "telemetria": procesarTelemetria,
    "eventos/tag": procesarEventoTag,
}
