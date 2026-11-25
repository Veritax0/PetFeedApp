import os
import tempfile

directorioTemporal = tempfile.mkdtemp()
os.environ["URL_BASE_DATOS"] = f"sqlite:///{directorioTemporal}/prueba.db"
os.environ["USUARIO_API"] = "admin"
os.environ["CLAVE_API"] = "clave"
os.environ["USAR_TLS"] = "false"
os.environ["SEGUNDOS_INACTIVIDAD_SESION"] = "45"

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from comedero.api import app, obtenerPublicador
from comedero.baseDatos import Base, crearSesionBd, crearTablas, motor
from comedero.receptorMensajes import ReceptorMensajes


class PublicadorFalso:
    def __init__(self) -> None:
        self.publicaciones: list[tuple[str, list[str]]] = []

    def publicarTagsAutorizados(self, comederoId: str, tagsAutorizados: list[str]) -> None:
        self.publicaciones.append((comederoId, list(tagsAutorizados)))


@pytest.fixture
def entorno():
    Base.metadata.drop_all(motor)
    crearTablas()
    publicador = PublicadorFalso()
    receptor = ReceptorMensajes(crearSesionBd, publicador)
    app.dependency_overrides[obtenerPublicador] = lambda: publicador
    clienteHttp = TestClient(app)
    clienteHttp.auth = ("admin", "clave")
    yield SimpleNamespace(api=clienteHttp, receptor=receptor, publicador=publicador)
    app.dependency_overrides.clear()
