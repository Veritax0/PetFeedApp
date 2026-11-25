from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from comedero.baseDatos import ahoraUtc, asegurarUtc
from comedero.excepciones import RecursoNoEncontrado
from comedero.modelos import (
    Calibracion,
    Comedero,
    ComederoMascota,
    EventoRfid,
    LecturaPeso,
    Mascota,
    SesionComida,
    TagRfid,
)
from comedero.servicios.comun import exigirComedero, serializarTag


def obtenerCalibracionActiva(sesionBd: Session, comederoId: str) -> Calibracion | None:
    consulta = select(Calibracion).where(
        Calibracion.comederoId == comederoId, Calibracion.activa.is_(True)
    )
    return sesionBd.scalars(consulta).first()


def convertirAGramos(pesoCrudo: float, calibracion: Calibracion | None) -> float | None:
    if calibracion is None:
        return None
    return round((pesoCrudo - calibracion.tara) / calibracion.factorEscala, 1)


def calcularConsumoSesion(
    sesionBd: Session, sesionComida: SesionComida, calibracion: Calibracion | None
) -> float | None:
    if calibracion is None:
        return None
    consulta = (
        select(LecturaPeso.pesoCrudo)
        .where(LecturaPeso.sesionId == sesionComida.id)
        .order_by(LecturaPeso.fecha)
    )
    pesosCrudos = sesionBd.scalars(consulta).all()
    if len(pesosCrudos) < 2:
        return None
    return round((pesosCrudos[0] - pesosCrudos[-1]) / calibracion.factorEscala, 1)


def listarMascotas(sesionBd: Session) -> list[dict]:
    tagsPorMascota: dict[int, list[dict]] = {}
    for tag in sesionBd.scalars(select(TagRfid)).all():
        tagsPorMascota.setdefault(tag.mascotaId, []).append(serializarTag(tag))
    mascotas = sesionBd.scalars(select(Mascota).order_by(Mascota.nombre)).all()
    return [
        {
            "id": mascota.id,
            "nombre": mascota.nombre,
            "fechaRegistro": mascota.fechaRegistro,
            "tags": tagsPorMascota.get(mascota.id, []),
        }
        for mascota in mascotas
    ]


def listarComederos(sesionBd: Session) -> list[dict]:
    mascotasPorComedero: dict[str, list[int]] = {}
    for asignacion in sesionBd.scalars(select(ComederoMascota)).all():
        mascotasPorComedero.setdefault(asignacion.comederoId, []).append(asignacion.mascotaId)
    comederos = sesionBd.scalars(select(Comedero).order_by(Comedero.id)).all()
    return [
        {
            "id": comedero.id,
            "nombre": comedero.nombre,
            "esNuevo": comedero.nombre is None,
            "ultimaConexion": comedero.ultimaConexion,
            "mascotaIds": mascotasPorComedero.get(comedero.id, []),
        }
        for comedero in comederos
    ]


def listarLecturas(
    sesionBd: Session,
    comederoId: str,
    desde: datetime | None,
    hasta: datetime | None,
    mascotaId: int | None,
    limite: int,
) -> list[dict]:
    exigirComedero(sesionBd, comederoId)
    consulta = select(LecturaPeso).where(LecturaPeso.comederoId == comederoId)
    if desde is not None:
        consulta = consulta.where(LecturaPeso.fecha >= asegurarUtc(desde))
    if hasta is not None:
        consulta = consulta.where(LecturaPeso.fecha <= asegurarUtc(hasta))
    if mascotaId is not None:
        consulta = consulta.where(LecturaPeso.mascotaId == mascotaId)
    lecturas = sesionBd.scalars(consulta.order_by(LecturaPeso.fecha.desc()).limit(limite)).all()
    calibracion = obtenerCalibracionActiva(sesionBd, comederoId)
    return [
        {
            "fecha": lectura.fecha,
            "pesoCrudo": lectura.pesoCrudo,
            "pesoGramos": convertirAGramos(lectura.pesoCrudo, calibracion),
            "mascotaId": lectura.mascotaId,
            "sesionId": lectura.sesionId,
        }
        for lectura in reversed(lecturas)
    ]


def listarSesiones(
    sesionBd: Session,
    comederoId: str,
    desde: datetime | None,
    hasta: datetime | None,
    mascotaId: int | None,
    limite: int,
) -> list[dict]:
    exigirComedero(sesionBd, comederoId)
    consulta = select(SesionComida).where(SesionComida.comederoId == comederoId)
    if desde is not None:
        consulta = consulta.where(SesionComida.inicio >= asegurarUtc(desde))
    if hasta is not None:
        consulta = consulta.where(SesionComida.inicio <= asegurarUtc(hasta))
    if mascotaId is not None:
        consulta = consulta.where(SesionComida.mascotaId == mascotaId)
    sesiones = sesionBd.scalars(consulta.order_by(SesionComida.inicio.desc()).limit(limite)).all()
    calibracion = obtenerCalibracionActiva(sesionBd, comederoId)
    return [
        {
            "id": sesion.id,
            "mascotaId": sesion.mascotaId,
            "inicio": sesion.inicio,
            "ultimaDeteccion": sesion.ultimaDeteccion,
            "fin": sesion.fin,
            "consumoGramos": calcularConsumoSesion(sesionBd, sesion, calibracion),
        }
        for sesion in sesiones
    ]


def obtenerPesoCrudoPromedio(sesionBd: Session, comederoId: str, ultimasLecturas: int) -> dict:
    exigirComedero(sesionBd, comederoId)
    consulta = (
        select(LecturaPeso.pesoCrudo)
        .where(LecturaPeso.comederoId == comederoId)
        .order_by(LecturaPeso.fecha.desc())
        .limit(ultimasLecturas)
    )
    pesosCrudos = sesionBd.scalars(consulta).all()
    if not pesosCrudos:
        raise RecursoNoEncontrado("El comedero aún no tiene lecturas")
    return {
        "pesoCrudoPromedio": sum(pesosCrudos) / len(pesosCrudos),
        "cantidadLecturas": len(pesosCrudos),
    }


def obtenerTagPendienteDeRegistro(
    sesionBd: Session, segundos: int, comederoId: str | None
) -> dict | None:
    desde = ahoraUtc() - timedelta(seconds=segundos)
    consulta = (
        select(EventoRfid)
        .where(EventoRfid.mascotaId.is_(None), EventoRfid.fecha >= desde)
        .order_by(EventoRfid.fecha.desc())
    )
    if comederoId is not None:
        consulta = consulta.where(EventoRfid.comederoId == comederoId)
    evento = sesionBd.scalars(consulta).first()
    if evento is None:
        return None
    return {"tagHex": evento.tagHex, "comederoId": evento.comederoId, "fecha": evento.fecha}
