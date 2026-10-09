import sqlite3
import time
from contextlib import closing

from .deye import Snapshot

SCHEMA = """CREATE TABLE IF NOT EXISTS samples (
    ts INTEGER PRIMARY KEY, pv REAL, load REAL, grid REAL, battery REAL, soc REAL)"""


class Store:
    def __init__(self, path):
        self.path = path
        with closing(self._conn()) as db, db:
            db.execute(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path)

    def add(self, s: Snapshot):
        with closing(self._conn()) as db, db:
            db.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?)",
                       (s.ts, s.pv_w, s.load_w, s.grid_w, s.battery_w, s.soc))

    def since(self, hours: float, now=None) -> list[Snapshot]:
        start = int((now or time.time()) - hours * 3600)
        with closing(self._conn()) as db:
            rows = db.execute("SELECT ts,pv,load,grid,battery,soc FROM samples WHERE ts>=? ORDER BY ts",
                              (start,)).fetchall()
        return [Snapshot(*r) for r in rows]
