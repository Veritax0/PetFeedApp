# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

import logging
import secrets
import threading
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from comedero.baseDatos import ahoraUtc, crearSesionBd, crearTablas
from comedero.composicion import construirClienteMqtt
from comedero.configuracion import configuracion
from comedero.excepciones import (
    ConflictoDeDatos,
    DatosInvalidos,
    ErrorDeDominio,
    RecursoNoEncontrado,
)
from comedero.puertos import PublicadorTagsAutorizados
from comedero.servicios import consultas, gestion, ingesta

registro = logging.getLogger("comedero.api")
seguridadBasica = HTTPBasic()
segundosEntreCierresDeSesion = 15
codigosHttpPorError: dict[type[ErrorDeDominio], int] = {
    RecursoNoEncontrado: status.HTTP_404_NOT_FOUND,
    ConflictoDeDatos: status.HTTP_409_CONFLICT,
    DatosInvalidos: 422,
}


class MascotaEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class TagEntrada(BaseModel):
    tagHex: str


class TagActivoEntrada(BaseModel):
    activo: bool


class ComederoEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class CalibracionEntrada(BaseModel):
    lecturaTara: float
    lecturaConPeso: float
    pesoReferenciaGramos: float


def exigirCredenciales(
    credenciales: Annotated[HTTPBasicCredentials, Depends(seguridadBasica)],
) -> None:
    usuarioEsValido = secrets.compare_digest(
        credenciales.username.encode(), configuracion.usuarioApi.encode()
    )
    claveEsValida = secrets.compare_digest(
        credenciales.password.encode(), configuracion.claveApi.encode()
    )
    if not (usuarioEsValido and claveEsValida):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )


def obtenerSesionBd():
    with crearSesionBd() as sesionBd:
        yield sesionBd


def obtenerPublicador(solicitud: Request) -> PublicadorTagsAutorizados:
    return solicitud.app.state.publicador


SesionBd = Annotated[Session, Depends(obtenerSesionBd)]
Publicador = Annotated[PublicadorTagsAutorizados, Depends(obtenerPublicador)]


def crearManejadorDeError(codigoHttp: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def manejarError(solicitud: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=codigoHttp, content={"detail": str(error)})

    return manejarError


def cerrarSesionesVencidasPeriodicamente(eventoDetencion: threading.Event) -> None:
    while not eventoDetencion.wait(segundosEntreCierresDeSesion):
        try:
            with crearSesionBd() as sesionBd:
                ingesta.cerrarSesionesVencidas(sesionBd, ahoraUtc())
                sesionBd.commit()
        except Exception:
            registro.exception("Error cerrando sesiones vencidas")


@asynccontextmanager
async def cicloVida(aplicacion: FastAPI):
    crearTablas()
    clienteMqtt = construirClienteMqtt()
    aplicacion.state.publicador = clienteMqtt
    eventoDetencion = threading.Event()
    hiloCierreSesiones = threading.Thread(
        target=cerrarSesionesVencidasPeriodicamente, args=(eventoDetencion,), daemon=True
    )
    hiloCierreSesiones.start()
    clienteMqtt.iniciar()
    yield
    clienteMqtt.detener()
    eventoDetencion.set()


aplicacion = FastAPI(
    title="Backend del comedero de mascotas",
    lifespan=cicloVida,
    dependencies=[Depends(exigirCredenciales)],
)
app = aplicacion

for tipoError, codigoHttp in codigosHttpPorError.items():
    aplicacion.add_exception_handler(tipoError, crearManejadorDeError(codigoHttp))


@aplicacion.get("/mascotas")
def listarMascotas(sesionBd: SesionBd):
    return consultas.listarMascotas(sesionBd)


@aplicacion.post("/mascotas", status_code=status.HTTP_201_CREATED)
def crearMascota(entrada: MascotaEntrada, sesionBd: SesionBd):
    return gestion.crearMascota(sesionBd, entrada.nombre)


@aplicacion.post("/mascotas/{mascotaId}/tags", status_code=status.HTTP_201_CREATED)
def registrarTag(mascotaId: int, entrada: TagEntrada, sesionBd: SesionBd, publicador: Publicador):
    return gestion.registrarTag(sesionBd, publicador, mascotaId, entrada.tagHex)


@aplicacion.patch("/tags/{tagId}")
def cambiarEstadoTag(
    tagId: int, entrada: TagActivoEntrada, sesionBd: SesionBd, publicador: Publicador
):
    return gestion.cambiarEstadoTag(sesionBd, publicador, tagId, entrada.activo)


@aplicacion.get("/tags/pendiente")
def obtenerTagPendienteDeRegistro(
    sesionBd: SesionBd,
    segundos: int = Query(60, ge=1, le=600),
    comederoId: str | None = None,
):
    return consultas.obtenerTagPendienteDeRegistro(sesionBd, segundos, comederoId)


@aplicacion.get("/comederos")
def listarComederos(sesionBd: SesionBd):
    return consultas.listarComederos(sesionBd)


@aplicacion.patch("/comederos/{comederoId}")
def renombrarComedero(comederoId: str, entrada: ComederoEntrada, sesionBd: SesionBd):
    return gestion.renombrarComedero(sesionBd, comederoId, entrada.nombre)


@aplicacion.put("/comederos/{comederoId}/mascotas/{mascotaId}")
def asignarMascotaAComedero(
    comederoId: str, mascotaId: int, sesionBd: SesionBd, publicador: Publicador
):
    return gestion.asignarMascotaAComedero(sesionBd, publicador, comederoId, mascotaId)


@aplicacion.delete("/comederos/{comederoId}/mascotas/{mascotaId}")
def quitarMascotaDeComedero(
    comederoId: str, mascotaId: int, sesionBd: SesionBd, publicador: Publicador
):
    return gestion.quitarMascotaDeComedero(sesionBd, publicador, comederoId, mascotaId)


@aplicacion.get("/comederos/{comederoId}/lecturas")
def listarLecturas(
    comederoId: str,
    sesionBd: SesionBd,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    mascotaId: int | None = None,
    limite: int = Query(1000, ge=1, le=10000),
):
    return consultas.listarLecturas(sesionBd, comederoId, desde, hasta, mascotaId, limite)


@aplicacion.get("/comederos/{comederoId}/sesiones")
def listarSesiones(
    comederoId: str,
    sesionBd: SesionBd,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    mascotaId: int | None = None,
    limite: int = Query(200, ge=1, le=2000),
):
    return consultas.listarSesiones(sesionBd, comederoId, desde, hasta, mascotaId, limite)


@aplicacion.get("/comederos/{comederoId}/pesoCrudoPromedio")
def obtenerPesoCrudoPromedio(
    comederoId: str, sesionBd: SesionBd, ultimasLecturas: int = Query(5, ge=1, le=100)
):
    return consultas.obtenerPesoCrudoPromedio(sesionBd, comederoId, ultimasLecturas)


@aplicacion.post("/comederos/{comederoId}/calibracion", status_code=status.HTTP_201_CREATED)
def calibrarComedero(comederoId: str, entrada: CalibracionEntrada, sesionBd: SesionBd):
    return gestion.calibrarComedero(
        sesionBd,
        comederoId,
        entrada.lecturaTara,
        entrada.lecturaConPeso,
        entrada.pesoReferenciaGramos,
    )
