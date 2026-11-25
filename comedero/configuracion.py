import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Configuracion:
    urlBaseDatos: str
    hostBroker: str
    puertoBroker: int
    usuarioBroker: str | None
    claveBroker: str | None
    usarTls: bool
    rutaCertificadoCa: str | None
    rutaCertificadoCliente: str | None
    rutaClaveCliente: str | None
    topicBase: str
    segundosInactividadSesion: int
    usuarioApi: str
    claveApi: str


def leerTextoOpcional(nombreVariable: str) -> str | None:
    return os.getenv(nombreVariable) or None


def leerBooleano(nombreVariable: str, valorPorDefecto: bool) -> bool:
    valor = os.getenv(nombreVariable)
    if valor is None or valor.strip() == "":
        return valorPorDefecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes")


def validarConfiguracionTls(
    usarTls: bool,
    rutaCertificadoCa: str | None,
    rutaCertificadoCliente: str | None,
    rutaClaveCliente: str | None,
) -> None:
    if not usarTls:
        return
    if rutaCertificadoCa is None:
        raise ValueError("RUTA_CA es obligatoria cuando USAR_TLS está activo")
    if (rutaCertificadoCliente is None) != (rutaClaveCliente is None):
        raise ValueError("RUTA_CERTIFICADO_CLIENTE y RUTA_CLAVE_CLIENTE se definen juntas")


def cargarConfiguracion() -> Configuracion:
    usarTls = leerBooleano("USAR_TLS", True)
    rutaCertificadoCa = leerTextoOpcional("RUTA_CA")
    rutaCertificadoCliente = leerTextoOpcional("RUTA_CERTIFICADO_CLIENTE")
    rutaClaveCliente = leerTextoOpcional("RUTA_CLAVE_CLIENTE")
    validarConfiguracionTls(usarTls, rutaCertificadoCa, rutaCertificadoCliente, rutaClaveCliente)
    return Configuracion(
        urlBaseDatos=os.getenv("URL_BASE_DATOS", "sqlite:///comedero.db"),
        hostBroker=os.getenv("HOST_BROKER", "localhost"),
        puertoBroker=int(os.getenv("PUERTO_BROKER") or (8883 if usarTls else 1883)),
        usuarioBroker=leerTextoOpcional("USUARIO_BROKER"),
        claveBroker=leerTextoOpcional("CLAVE_BROKER"),
        usarTls=usarTls,
        rutaCertificadoCa=rutaCertificadoCa,
        rutaCertificadoCliente=rutaCertificadoCliente,
        rutaClaveCliente=rutaClaveCliente,
        topicBase=os.getenv("TOPIC_BASE", "lab/jjjteam"),
        segundosInactividadSesion=int(os.getenv("SEGUNDOS_INACTIVIDAD_SESION", "45")),
        usuarioApi=os.environ["USUARIO_API"],
        claveApi=os.environ["CLAVE_API"],
    )


configuracion = cargarConfiguracion()
