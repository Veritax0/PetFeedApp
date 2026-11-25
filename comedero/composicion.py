from comedero.baseDatos import crearSesionBd
from comedero.clienteMqtt import ClienteMqtt
from comedero.configuracion import configuracion
from comedero.receptorMensajes import ReceptorMensajes


def construirClienteMqtt() -> ClienteMqtt:
    clienteMqtt = ClienteMqtt(configuracion)
    receptorMensajes = ReceptorMensajes(crearSesionBd, clienteMqtt)
    clienteMqtt.alRecibirMensaje = receptorMensajes.recibir
    clienteMqtt.alConectar = receptorMensajes.republicarTodosLosComederos
    return clienteMqtt
