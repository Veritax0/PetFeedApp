import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from comedero.baseDatos import ahoraUtc
from comedero.puertos import PublicadorTagsAutorizados
from comedero.servicios import gestion, ingesta
from comedero.servicios.ingesta import ManejadorMensaje

registro = logging.getLogger("comedero.receptor")


class ReceptorMensajes:
    def __init__(
        self,
        fabricaSesionBd: Callable[[], Session],
        publicador: PublicadorTagsAutorizados,
        manejadores: dict[str, ManejadorMensaje] | None = None,
    ) -> None:
        self.fabricaSesionBd = fabricaSesionBd
        self.publicador = publicador
        self.manejadores = (
            manejadores if manejadores is not None else ingesta.manejadoresPorTipoMensaje
        )

    def recibir(self, comederoId: str, tipoMensaje: str, datos: dict) -> None:
        manejador = self.manejadores.get(tipoMensaje)
        if manejador is None:
            registro.warning("Tipo de mensaje sin manejador: %s", tipoMensaje)
            return
        ahora = ahoraUtc()
        with self.fabricaSesionBd() as sesionBd:
            _, comederoEsNuevo = ingesta.obtenerOCrearComedero(sesionBd, comederoId, ahora)
            manejador(sesionBd, comederoId, datos, ahora)
            sesionBd.commit()
            if comederoEsNuevo:
                gestion.publicarTagsAutorizadosDeComedero(sesionBd, self.publicador, comederoId)

    def republicarTodosLosComederos(self) -> None:
        with self.fabricaSesionBd() as sesionBd:
            gestion.publicarTagsAutorizadosDeTodosLosComederos(sesionBd, self.publicador)
