#!/usr/bin/env bash
set -euo pipefail

nombreHost="${1:-$(hostname)}"
directorioCertificados="${DIRECTORIO_CERTIFICADOS:-$HOME/mqtt_certs}"
directorioMosquitto="/etc/mosquitto"
directorioScript="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
diasCa=3650
diasServidor=825

if [[ $EUID -eq 0 ]]; then
    ejecutarPrivilegiado() { "$@"; }
else
    ejecutarPrivilegiado() { sudo "$@"; }
fi

generarAutoridadCertificadora() {
    if [[ -f ca.key && -f ca.crt ]]; then
        echo "Se reutiliza la CA existente en $directorioCertificados"
        return
    fi
    openssl genrsa -out ca.key 2048
    openssl req -new -x509 -sha256 -days "$diasCa" -key ca.key -out ca.crt \
        -subj "/CN=CA-Comedero" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign"
    chmod 600 ca.key
}

generarCertificadoDelBroker() {
    openssl genrsa -out server.key 2048
    openssl req -new -sha256 -key server.key -out server.csr -subj "/CN=${nombreHost}.local"
    printf "subjectAltName=DNS:%s.local,DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n" \
        "$nombreHost" > server.ext
    openssl x509 -req -sha256 -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
        -out server.crt -days "$diasServidor" -extfile server.ext
    openssl verify -CAfile ca.crt server.crt
}

instalarCertificadosYConfiguracion() {
    ejecutarPrivilegiado mkdir -p "$directorioMosquitto/certs" "$directorioMosquitto/conf.d"
    ejecutarPrivilegiado cp ca.crt server.crt server.key "$directorioMosquitto/certs/"
    ejecutarPrivilegiado chown mosquitto: \
        "$directorioMosquitto/certs/ca.crt" \
        "$directorioMosquitto/certs/server.crt" \
        "$directorioMosquitto/certs/server.key"
    ejecutarPrivilegiado chmod 644 "$directorioMosquitto/certs/ca.crt" "$directorioMosquitto/certs/server.crt"
    ejecutarPrivilegiado chmod 640 "$directorioMosquitto/certs/server.key"
    ejecutarPrivilegiado cp "$directorioScript/tls.conf" "$directorioMosquitto/conf.d/tls.conf"
    ejecutarPrivilegiado cp "$directorioScript/acl.conf" "$directorioMosquitto/acl.conf"
    ejecutarPrivilegiado chown mosquitto: "$directorioMosquitto/acl.conf"
    ejecutarPrivilegiado chmod 640 "$directorioMosquitto/acl.conf"
}

crearUsuariosDelBroker() {
    local archivoClaves="$directorioMosquitto/passwd"
    ejecutarPrivilegiado touch "$archivoClaves"
    ejecutarPrivilegiado chmod 600 "$archivoClaves"
    for usuario in backend comederos; do
        local variableClave="CLAVE_${usuario^^}"
        if [[ -n "${!variableClave:-}" ]]; then
            ejecutarPrivilegiado mosquitto_passwd -b "$archivoClaves" "$usuario" "${!variableClave}"
        else
            ejecutarPrivilegiado mosquitto_passwd "$archivoClaves" "$usuario"
        fi
    done
    ejecutarPrivilegiado chown mosquitto: "$archivoClaves"
    ejecutarPrivilegiado chmod 640 "$archivoClaves"
}

reiniciarMosquitto() {
    if [[ "${SALTAR_REINICIO:-0}" == "1" ]]; then
        return
    fi
    ejecutarPrivilegiado systemctl restart mosquitto
    ejecutarPrivilegiado systemctl --no-pager status mosquitto | head -n 5
}

mkdir -p "$directorioCertificados"
cd "$directorioCertificados"
generarAutoridadCertificadora
generarCertificadoDelBroker
instalarCertificadosYConfiguracion
crearUsuariosDelBroker
reiniciarMosquitto
echo "Copia $directorioCertificados/ca.crt a src/ca.crt en el proyecto del ESP32"
