from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator

from comedero.configuracion import configuracion


class FechaUtc(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, valor, dialecto):
        if valor is None:
            return None
        return valor.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, valor, dialecto):
        if valor is None:
            return None
        return valor.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


esSqlite = configuracion.urlBaseDatos.startswith("sqlite")

motor = create_engine(
    configuracion.urlBaseDatos,
    connect_args={"check_same_thread": False, "timeout": 30} if esSqlite else {},
    pool_pre_ping=True,
)

if esSqlite:

    @event.listens_for(motor, "connect")
    def configurarConexionSqlite(conexionDbapi, registroConexion):
        cursor = conexionDbapi.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


crearSesionBd = sessionmaker(bind=motor, expire_on_commit=False)


def ahoraUtc() -> datetime:
    return datetime.now(timezone.utc)


def asegurarUtc(fecha: datetime | None) -> datetime | None:
    if fecha is not None and fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)
    return fecha


def crearTablas() -> None:
    import comedero.modelos

    Base.metadata.create_all(motor)
