from sqlalchemy.orm import Session

from comedero.excepciones import RecursoNoEncontrado
from comedero.modelos import Comedero, Mascota, TagRfid


def exigirMascota(sesionBd: Session, mascotaId: int) -> Mascota:
    mascota = sesionBd.get(Mascota, mascotaId)
    if mascota is None:
        raise RecursoNoEncontrado("Mascota no encontrada")
    return mascota


def exigirComedero(sesionBd: Session, comederoId: str) -> Comedero:
    comedero = sesionBd.get(Comedero, comederoId)
    if comedero is None:
        raise RecursoNoEncontrado("Comedero no encontrado")
    return comedero


def serializarTag(tag: TagRfid) -> dict:
    return {"id": tag.id, "tagHex": tag.tagHex, "activo": tag.activo}
