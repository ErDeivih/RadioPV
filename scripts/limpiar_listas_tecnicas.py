"""Borra las listas generadas con nombre técnico («Top 12», «Subiendo 12»).

Las creaba `rebuild_home_tops` con el id del usuario dentro del nombre y sin dueño, así que
aparecían en las listas destacadas de todo el mundo con un nombre que parecía un error. El código
ya genera «Tus más escuchadas» y «Descubrimientos de la semana», con dueño; esto sólo quita las
viejas para que no se queden ahí para siempre.

Uso (dentro del contenedor del API):
    docker exec radiopv-api python3 /tmp/limpiar_listas.py            # sólo informa
    docker exec radiopv-api python3 /tmp/limpiar_listas.py --apply
"""
import re
import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402

VIEJO = re.compile(r"^(Top|Subiendo) \d+$")

db = SessionLocal()
apply = "--apply" in sys.argv

candidatas = [p for p in db.query(models.Playlist).filter_by(type="system").all()
              if VIEJO.match(p.name or "")]
print(f"listas con nombre técnico: {len(candidatas)}")
for p in candidatas[:10]:
    n = db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).count()
    print(f"   {p.id:5d}  {p.name!r}  dueño={p.user_id}  {n} canciones")
if len(candidatas) > 10:
    print(f"   ... y {len(candidatas) - 10} más")

print("\nlistas personales con nombre nuevo:")
for p in db.query(models.Playlist).filter(models.Playlist.user_id.isnot(None)).all():
    n = db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).count()
    print(f"   {p.id:5d}  {p.name!r}  dueño={p.user_id}  {n} canciones")

if not apply:
    print("\n[..] sólo información: añade --apply para borrar las técnicas")
else:
    for p in candidatas:
        db.query(models.PlaylistTrack).filter_by(playlist_id=p.id).delete()
        db.delete(p)
    db.commit()
    print(f"\n[OK] borradas {len(candidatas)} listas con nombre técnico")

db.close()
