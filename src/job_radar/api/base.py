"""Lo común de la API: la conexión al almacén por petición y las rutas de los ficheros."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import sqlite_utils
from fastapi import Request


def bd(request: Request) -> Iterator[sqlite_utils.Database]:
    """Una conexión por petición. Con WAL, la web lee mientras la ingesta escribe."""
    conexion = sqlite3.connect(request.app.state.ruta_db, check_same_thread=False)
    conexion.row_factory = sqlite3.Row
    db = sqlite_utils.Database(conexion)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 15000")  # si la ingesta está escribiendo, espera en vez de fallar
    try:
        yield db
    finally:
        conexion.close()


def datos(request: Request) -> Path:
    return request.app.state.datos
