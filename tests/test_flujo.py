from datetime import timedelta

from comedero.baseDatos import ahoraUtc, crearSesionBd
from comedero.receptorMensajes import ReceptorMensajes
from comedero.servicios import ingesta

comederoId = "AABBCCDDEEFF"
tagHex = "0A1B2C3D4E"


def prepararMascotaConTag(entorno) -> int:
    entorno.receptor.recibir(comederoId, "telemetria", {"peso_crudo": 113700})
    mascotaId = entorno.api.post("/mascotas", json={"nombre": "Luna"}).json()["id"]
    entorno.api.post(f"/mascotas/{mascotaId}/tags", json={"tagHex": tagHex.lower()})
    entorno.api.put(f"/comederos/{comederoId}/mascotas/{mascotaId}")
    return mascotaId


def test_api_exige_credenciales(entorno):
    entorno.api.auth = None
    assert entorno.api.get("/mascotas").status_code == 401


def test_comedero_nuevo_recibe_lista_vacia(entorno):
    entorno.receptor.recibir(comederoId, "telemetria", {"peso_crudo": 113700})
    assert entorno.publicador.publicaciones == [(comederoId, [])]
    assert entorno.api.get("/comederos").json()[0]["esNuevo"] is True


def test_tag_desconocido_queda_pendiente_y_se_registra(entorno):
    entorno.receptor.recibir(comederoId, "eventos/tag", {"hex": tagHex})
    pendiente = entorno.api.get("/tags/pendiente").json()
    assert pendiente["tagHex"] == tagHex
    mascotaId = entorno.api.post("/mascotas", json={"nombre": "Luna"}).json()["id"]
    respuesta = entorno.api.post(f"/mascotas/{mascotaId}/tags", json={"tagHex": pendiente["tagHex"]})
    assert respuesta.status_code == 201
    duplicado = entorno.api.post(f"/mascotas/{mascotaId}/tags", json={"tagHex": tagHex})
    assert duplicado.status_code == 409
    formatoInvalido = entorno.api.post(f"/mascotas/{mascotaId}/tags", json={"tagHex": "XYZ"})
    assert formatoInvalido.status_code == 422


def test_asignacion_y_estado_del_tag_republican_la_lista(entorno):
    mascotaId = prepararMascotaConTag(entorno)
    assert entorno.publicador.publicaciones[-1] == (comederoId, [tagHex])
    tagId = entorno.api.get("/mascotas").json()[0]["tags"][0]["id"]
    entorno.api.patch(f"/tags/{tagId}", json={"activo": False})
    assert entorno.publicador.publicaciones[-1] == (comederoId, [])
    entorno.api.patch(f"/tags/{tagId}", json={"activo": True})
    entorno.api.delete(f"/comederos/{comederoId}/mascotas/{mascotaId}")
    assert entorno.publicador.publicaciones[-1] == (comederoId, [])


def test_tag_de_otra_mascota_no_abre_sesion(entorno):
    entorno.receptor.recibir(comederoId, "telemetria", {"peso_crudo": 113700})
    mascotaId = entorno.api.post("/mascotas", json={"nombre": "Max"}).json()["id"]
    entorno.api.post(f"/mascotas/{mascotaId}/tags", json={"tagHex": tagHex})
    entorno.receptor.recibir(comederoId, "eventos/tag", {"hex": tagHex})
    assert entorno.api.get(f"/comederos/{comederoId}/sesiones").json() == []


def test_sesion_asocia_peso_a_la_mascota_y_calcula_consumo(entorno):
    mascotaId = prepararMascotaConTag(entorno)
    entorno.api.post(
        f"/comederos/{comederoId}/calibracion",
        json={"lecturaTara": 113700, "lecturaConPeso": 123700, "pesoReferenciaGramos": 200},
    )
    entorno.receptor.recibir(comederoId, "eventos/tag", {"hex": tagHex})
    entorno.receptor.recibir(comederoId, "telemetria", {"peso_crudo": 120000})
    entorno.receptor.recibir(comederoId, "eventos/tag", {"hex": tagHex})
    entorno.receptor.recibir(comederoId, "telemetria", {"peso_crudo": 118000})
    with crearSesionBd() as sesionBd:
        ingesta.cerrarSesionesVencidas(sesionBd, ahoraUtc() + timedelta(minutes=5))
        sesionBd.commit()
    entorno.receptor.recibir(comederoId, "telemetria", {"peso_crudo": 117000})
    lecturas = entorno.api.get(f"/comederos/{comederoId}/lecturas").json()
    assert [lectura["mascotaId"] for lectura in lecturas[-3:]] == [mascotaId, mascotaId, None]
    sesion = entorno.api.get(f"/comederos/{comederoId}/sesiones").json()[0]
    assert sesion["fin"] is not None
    assert sesion["consumoGramos"] == 40.0


def test_calibracion_con_lecturas_iguales_responde_422(entorno):
    entorno.receptor.recibir(comederoId, "telemetria", {"peso_crudo": 113700})
    respuesta = entorno.api.post(
        f"/comederos/{comederoId}/calibracion",
        json={"lecturaTara": 1, "lecturaConPeso": 1, "pesoReferenciaGramos": 100},
    )
    assert respuesta.status_code == 422


def test_receptor_usa_el_registro_de_manejadores_inyectado(entorno):
    recibidos = []
    receptor = ReceptorMensajes(
        crearSesionBd,
        entorno.publicador,
        {"estado": lambda sesionBd, comedero, datos, ahora: recibidos.append((comedero, datos))},
    )
    receptor.recibir(comederoId, "estado", {"ok": True})
    receptor.recibir(comederoId, "desconocido", {})
    assert recibidos == [(comederoId, {"ok": True})]
