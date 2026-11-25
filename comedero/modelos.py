from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from comedero.baseDatos import Base, FechaUtc


class Mascota(Base):
    __tablename__ = "mascotas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    fechaRegistro: Mapped[datetime] = mapped_column(FechaUtc)


class TagRfid(Base):
    __tablename__ = "tags_rfid"

    id: Mapped[int] = mapped_column(primary_key=True)
    tagHex: Mapped[str] = mapped_column(String(16), unique=True)
    mascotaId: Mapped[int] = mapped_column(ForeignKey("mascotas.id", ondelete="CASCADE"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Comedero(Base):
    __tablename__ = "comederos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    nombre: Mapped[str | None] = mapped_column(String(100), default=None)
    ultimaConexion: Mapped[datetime | None] = mapped_column(FechaUtc, default=None)


class ComederoMascota(Base):
    __tablename__ = "comedero_mascotas"

    comederoId: Mapped[str] = mapped_column(
        ForeignKey("comederos.id", ondelete="CASCADE"), primary_key=True
    )
    mascotaId: Mapped[int] = mapped_column(
        ForeignKey("mascotas.id", ondelete="CASCADE"), primary_key=True
    )


class SesionComida(Base):
    __tablename__ = "sesiones_comida"
    __table_args__ = (Index("ix_sesiones_comedero_fin", "comederoId", "fin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    comederoId: Mapped[str] = mapped_column(ForeignKey("comederos.id", ondelete="CASCADE"))
    mascotaId: Mapped[int] = mapped_column(ForeignKey("mascotas.id", ondelete="CASCADE"))
    inicio: Mapped[datetime] = mapped_column(FechaUtc)
    ultimaDeteccion: Mapped[datetime] = mapped_column(FechaUtc)
    fin: Mapped[datetime | None] = mapped_column(FechaUtc, default=None)


class LecturaPeso(Base):
    __tablename__ = "lecturas_peso"
    __table_args__ = (Index("ix_lecturas_comedero_fecha", "comederoId", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    comederoId: Mapped[str] = mapped_column(ForeignKey("comederos.id", ondelete="CASCADE"))
    mascotaId: Mapped[int | None] = mapped_column(
        ForeignKey("mascotas.id", ondelete="SET NULL"), default=None
    )
    sesionId: Mapped[int | None] = mapped_column(
        ForeignKey("sesiones_comida.id", ondelete="SET NULL"), default=None
    )
    fecha: Mapped[datetime] = mapped_column(FechaUtc)
    pesoCrudo: Mapped[int] = mapped_column(Integer)


class EventoRfid(Base):
    __tablename__ = "eventos_rfid"
    __table_args__ = (Index("ix_eventos_fecha", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    comederoId: Mapped[str] = mapped_column(ForeignKey("comederos.id", ondelete="CASCADE"))
    fecha: Mapped[datetime] = mapped_column(FechaUtc)
    tagHex: Mapped[str] = mapped_column(String(16))
    mascotaId: Mapped[int | None] = mapped_column(
        ForeignKey("mascotas.id", ondelete="SET NULL"), default=None
    )
    autorizado: Mapped[bool] = mapped_column(Boolean)


class Calibracion(Base):
    __tablename__ = "calibraciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    comederoId: Mapped[str] = mapped_column(ForeignKey("comederos.id", ondelete="CASCADE"))
    fecha: Mapped[datetime] = mapped_column(FechaUtc)
    tara: Mapped[float] = mapped_column(Float)
    factorEscala: Mapped[float] = mapped_column(Float)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
