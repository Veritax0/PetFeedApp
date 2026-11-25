import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from comedero.baseDatos import ahoraUtc
from comedero.excepciones import ConflictoDeDatos, DatosInvalidos, RecursoNoEncontrado
from comedero.modelos import Calibracion, Comedero, ComederoMascota, Mascota, TagRfid
from comedero.puertos import PublicadorTagsAutorizados
from comedero.servicios.comun import (
    exigirComedero,
    exigirMascota,
    serializarTag,
)

patronTagHex = re.compile(r"^[0-9A-F]{10}$")


def obtenerTagsAutorizados(sesionBd: Session, comederoId: str) -> list[str]:
    consulta = (
        select(TagRfid.tagHex)
        .join(ComederoMascota, ComederoMascota.mascotaId == TagRfid.mascotaId)
        .where(ComederoMascota.comederoId == comederoId, TagRfid.activo.is_(True))
    )
    return sorted(sesionBd.scalars(consulta).all())


def obtenerIdsComederos(sesionBd: Session) -> list[str]:
    return list(sesionBd.scalars(select(Comedero.id)).all())


def obtenerComederosDeMascota(sesionBd: Session, mascotaId: int) -> list[str]:
    consulta = select(ComederoMascota.comederoId).where(ComederoMascota.mascotaId == mascotaId)
    return list(sesionBd.scalars(consulta).all())


def publicarTagsAutorizadosDeComedero(
    sesionBd: Session, publicador: PublicadorTagsAutorizados, comederoId: str
) -> None:
    publicador.publicarTagsAutorizados(comederoId, obtenerTagsAutorizados(sesionBd, comederoId))


def publicarTagsAutorizadosDeTodosLosComederos(
    sesionBd: Session, publicador: PublicadorTagsAutorizados
) -> None:
    for comederoId in obtenerIdsComederos(sesionBd):
        publicarTagsAutorizadosDeComedero(sesionBd, publicador, comederoId)


def publicarTagsAutorizadosDeMascota(
    sesionBd: Session, publicador: PublicadorTagsAutorizados, mascotaId: int
) -> None:
    for comederoId in obtenerComederosDeMascota(sesionBd, mascotaId):
        publicarTagsAutorizadosDeComedero(sesionBd, publicador, comederoId)


def crearMascota(sesionBd: Session, nombre: str) -> dict:
    mascota = Mascota(nombre=nombre.strip(), fechaRegistro=ahoraUtc())
    sesionBd.add(mascota)
    sesionBd.commit()
    return {"id": mascota.id, "nombre": mascota.nombre, "fechaRegistro": mascota.fechaRegistro}


def registrarTag(
    sesionBd: Session, publicador: PublicadorTagsAutorizados, mascotaId: int, tagHex: str
) -> dict:
    exigirMascota(sesionBd, mascotaId)
    tagNormalizado = tagHex.strip().upper()
    if not patronTagHex.match(tagNormalizado):
        raise DatosInvalidos("El tag debe tener 10 caracteres hexadecimales")
    tag = TagRfid(tagHex=tagNormalizado, mascotaId=mascotaId, activo=True)
    sesionBd.add(tag)
    try:
        sesionBd.commit()
    except IntegrityError:
        sesionBd.rollback()
        raise ConflictoDeDatos("El tag ya está registrado")
    publicarTagsAutorizadosDeMascota(sesionBd, publicador, mascotaId)
    return serializarTag(tag)


def cambiarEstadoTag(
    sesionBd: Session, publicador: PublicadorTagsAutorizados, tagId: int, activo: bool
) -> dict:
    tag = sesionBd.get(TagRfid, tagId)
    if tag is None:
        raise RecursoNoEncontrado("Tag no encontrado")
    tag.activo = activo
    sesionBd.commit()
    publicarTagsAutorizadosDeMascota(sesionBd, publicador, tag.mascotaId)
    return serializarTag(tag)


def renombrarComedero(sesionBd: Session, comederoId: str, nombre: str) -> dict:
    comedero = exigirComedero(sesionBd, comederoId)
    comedero.nombre = nombre.strip()
    sesionBd.commit()
    return {"id": comedero.id, "nombre": comedero.nombre}


def asignarMascotaAComedero(
    sesionBd: Session, publicador: PublicadorTagsAutorizados, comederoId: str, mascotaId: int
) -> dict:
    exigirComedero(sesionBd, comederoId)
    exigirMascota(sesionBd, mascotaId)
    if sesionBd.get(ComederoMascota, (comederoId, mascotaId)) is None:
        sesionBd.add(ComederoMascota(comederoId=comederoId, mascotaId=mascotaId))
        sesionBd.commit()
    publicarTagsAutorizadosDeComedero(sesionBd, publicador, comederoId)
    return {"comederoId": comederoId, "mascotaId": mascotaId}


def quitarMascotaDeComedero(
    sesionBd: Session, publicador: PublicadorTagsAutorizados, comederoId: str, mascotaId: int
) -> dict:
    asignacion = sesionBd.get(ComederoMascota, (comederoId, mascotaId))
    if asignacion is None:
        raise RecursoNoEncontrado("Asignación no encontrada")
    sesionBd.delete(asignacion)
    sesionBd.commit()
    publicarTagsAutorizadosDeComedero(sesionBd, publicador, comederoId)
    return {"comederoId": comederoId, "mascotaId": mascotaId}


def calibrarComedero(
    sesionBd: Session,
    comederoId: str,
    lecturaTara: float,
    lecturaConPeso: float,
    pesoReferenciaGramos: float,
) -> dict:
    exigirComedero(sesionBd, comederoId)
    if pesoReferenciaGramos <= 0:
        raise DatosInvalidos("El peso de referencia debe ser mayor que cero")
    factorEscala = (lecturaConPeso - lecturaTara) / pesoReferenciaGramos
    if factorEscala == 0:
        raise DatosInvalidos("Las lecturas con y sin peso no pueden ser iguales")
    calibracionesAnteriores = sesionBd.scalars(
        select(Calibracion).where(
            Calibracion.comederoId == comederoId, Calibracion.activa.is_(True)
        )
    ).all()
    for calibracionAnterior in calibracionesAnteriores:
        calibracionAnterior.activa = False
    calibracion = Calibracion(
        comederoId=comederoId,
        fecha=ahoraUtc(),
        tara=lecturaTara,
        factorEscala=factorEscala,
        activa=True,
    )
    sesionBd.add(calibracion)
    sesionBd.commit()
    return {
        "id": calibracion.id,
        "tara": calibracion.tara,
        "factorEscala": calibracion.factorEscala,
        "fecha": calibracion.fecha,
    }
