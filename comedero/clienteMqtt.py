import json
import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt

from comedero.configuracion import Configuracion

registro = logging.getLogger("comedero.mqtt")

CallbackMensaje = Callable[[str, str, dict], None]
CallbackConexion = Callable[[], None]


class ClienteMqtt:
    def __init__(self, configuracion: Configuracion) -> None:
        self.configuracion = configuracion
        self.alRecibirMensaje: CallbackMensaje | None = None
        self.alConectar: CallbackConexion | None = None
        self.cliente = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="comedero-backend"
        )
        self.configurarAutenticacion()
        self.configurarTls()
        self.cliente.reconnect_delay_set(min_delay=1, max_delay=30)
        self.cliente.on_connect = self.manejarConexion
        self.cliente.on_connect_fail = self.manejarFalloDeConexion
        self.cliente.on_message = self.manejarMensaje

    def configurarAutenticacion(self) -> None:
        if self.configuracion.usuarioBroker:
            self.cliente.username_pw_set(
                self.configuracion.usuarioBroker, self.configuracion.claveBroker
            )

    def configurarTls(self) -> None:
        if not self.configuracion.usarTls:
            registro.warning("TLS desactivado: la comunicación con el broker viaja sin cifrar")
            return
        self.cliente.tls_set(
            ca_certs=self.configuracion.rutaCertificadoCa,
            certfile=self.configuracion.rutaCertificadoCliente,
            keyfile=self.configuracion.rutaClaveCliente,
        )
        self.cliente.tls_insecure_set(False)

    def iniciar(self) -> None:
        self.cliente.connect_async(
            self.configuracion.hostBroker, self.configuracion.puertoBroker, keepalive=60
        )
        self.cliente.loop_start()

    def detener(self) -> None:
        self.cliente.disconnect()
        self.cliente.loop_stop()

    def manejarConexion(self, cliente, datosUsuario, banderas, codigoRazon, propiedades) -> None:
        if codigoRazon.is_failure:
            registro.error("Conexión rechazada por el broker: %s", codigoRazon)
            return
        topicBase = self.configuracion.topicBase
        cliente.subscribe([(f"{topicBase}/+/telemetria", 1), (f"{topicBase}/+/eventos/tag", 1)])
        if self.alConectar is not None:
            try:
                self.alConectar()
            except Exception:
                registro.exception("Error ejecutando las tareas posteriores a la conexión")

    def manejarFalloDeConexion(self, cliente, datosUsuario) -> None:
        registro.warning(
            "No se pudo conectar con el broker %s:%s (revisa red, certificado TLS y credenciales)",
            self.configuracion.hostBroker,
            self.configuracion.puertoBroker,
        )

    def manejarMensaje(self, cliente, datosUsuario, mensaje) -> None:
        try:
            comederoId, tipoMensaje = self.interpretarTopic(mensaje.topic)
            datos = json.loads(mensaje.payload)
            if not isinstance(datos, dict):
                raise ValueError("El mensaje no es un objeto JSON")
            if self.alRecibirMensaje is not None:
                self.alRecibirMensaje(comederoId, tipoMensaje, datos)
        except Exception:
            registro.exception("Error procesando el mensaje de %s", mensaje.topic)

    def interpretarTopic(self, topic: str) -> tuple[str, str]:
        segmentos = topic.removeprefix(f"{self.configuracion.topicBase}/").split("/")
        return segmentos[0], "/".join(segmentos[1:])

    def publicarTagsAutorizados(self, comederoId: str, tagsAutorizados: list[str]) -> None:
        self.cliente.publish(
            f"{self.configuracion.topicBase}/{comederoId}/tags_autorizados",
            json.dumps({"tags": tagsAutorizados}),
            qos=1,
            retain=True,
        )
