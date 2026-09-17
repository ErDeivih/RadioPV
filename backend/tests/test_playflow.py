"""Play-flow como lo hace el cliente: /auth/stream-token → /stream/{id}?t= con Range.

Verifica la secuencia real del reproductor (gesto del usuario + <audio> + seek), que el navegador
necesita las cabeceras CORS expuestas (Content-Range/Accept-Ranges/Content-Length) para el seek,
y que el token de streaming se puede refrescar antes de caducar a mitad de canción.
"""
import os


def test_playflow_stream_token_y_range(client):
    from app.database import SessionLocal
    from app import models
    music = os.environ["MUSIC_ROOT"]
    d = os.path.join(music, "catalogada", "Playflow")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, "tema.mp3")
    with open(fp, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" + b"\x00" * 8192)
    try:
        db = SessionLocal()
        tr = models.Track(title="PF", artist="PFArtist", file_path=fp,
                          status="descargada", source="test")
        db.add(tr)
        db.commit()
        db.refresh(tr)
        tid = tr.id
        db.close()

        # 1) el cliente se autentica y pide un token de streaming
        client.post("/auth/register", json={"email": "pf@t.com", "password": "clave-larga-1"})
        access = client.post("/auth/login", data={"username": "pf@t.com",
                                                  "password": "clave-larga-1"}).json()["access_token"]

        st = client.post("/auth/stream-token",
                         headers={"Authorization": f"Bearer {access}"}).json()["token"]

        # 2) <audio src="/stream/{id}?t=..."> con Range para el seek (con Origin → CORS)
        origin = {"Origin": "http://localhost:3000"}
        r = client.get(f"/stream/{tid}?t={st}", headers={**origin, "Range": "bytes=0-1023"})
        assert r.status_code == 206, r.content
        cr = r.headers.get("content-range", "")
        assert cr.startswith("bytes 0-1023/"), cr
        assert "accept-ranges" in r.headers
        assert "content-length" in r.headers

        # 3) las cabeceras de Range deben estar EXPUESTAS al navegador (CORS) para que el seek vea 206
        exposed = r.headers.get("access-control-expose-headers", "")
        for h in ("Content-Range", "Accept-Ranges", "Content-Length", "X-Total-Count"):
            assert h in exposed, f"{h} no expuesto: {exposed}"

        # 4) sin token → no sirve (401 por token ausente/inválido)
        assert client.get(f"/stream/{tid}", headers=origin).status_code in (401, 422)
        assert client.get(f"/stream/{tid}?t=basura", headers=origin).status_code in (401, 422)

        # 5) refresco del token (el cliente lo renueva con 60 s de margen antes de caducar):
        #    un token nuevo de /auth/stream-token sigue valiendo → la canción no se corta a mitad
        st2 = client.post("/auth/stream-token",
                          headers={"Authorization": f"Bearer {access}"}).json()["token"]
        r2 = client.get(f"/stream/{tid}?t={st2}", headers={**origin, "Range": "bytes=0-1023"})
        assert r2.status_code == 206
        assert r2.headers.get("content-range", "").startswith("bytes 0-1023/")
    finally:
        if os.path.exists(fp):
            os.unlink(fp)


def test_stream_410_si_fichero_falta(client):
    """Si el catálogo conoce la canción pero el fichero ya no está en disco → 410."""
    import os
    from app.database import SessionLocal
    from app import models
    music = os.environ["MUSIC_ROOT"]
    fp = os.path.join(music, "catalogada", "NoExiste", "perdido.mp3")  # no se crea
    db = SessionLocal()
    tr = models.Track(title="Perdida", artist="A", file_path=fp, status="descargada", source="test")
    db.add(tr)
    db.commit()
    db.refresh(tr)
    tid = tr.id
    db.close()

    client.post("/auth/register", json={"email": "pf2@t.com", "password": "clave-larga-1"})
    access = client.post("/auth/login", data={"username": "pf2@t.com",
                                              "password": "clave-larga-1"}).json()["access_token"]
    st = client.post("/auth/stream-token",
                     headers={"Authorization": f"Bearer {access}"}).json()["token"]
    r = client.get(f"/stream/{tid}?t={st}")
    assert r.status_code == 410, r.status_code


def test_stream_rechaza_token_de_acceso(client):
    """El token de acceso (scope=access) NO sirve en /stream; solo vale el de scope=stream."""
    from app.database import SessionLocal
    from app import models
    music = os.environ["MUSIC_ROOT"]
    d = os.path.join(music, "catalogada", "Scope")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, "tema.mp3")
    with open(fp, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" + b"\x00" * 4096)
    try:
        db = SessionLocal()
        tr = models.Track(title="Scope", artist="A", file_path=fp, status="descargada", source="test")
        db.add(tr)
        db.commit()
        db.refresh(tr)
        tid = tr.id
        db.close()

        access = client.post("/auth/login", data={"username": "pf2@t.com",
                                                  "password": "clave-larga-1"}).json()["access_token"]
        # token de acceso como si fuera de streaming → 401 (ámbito incorrecto)
        r = client.get(f"/stream/{tid}?t={access}")
        assert r.status_code == 401, r.status_code
    finally:
        if os.path.exists(fp):
            os.unlink(fp)


def test_stream_token_expira_en_futuro(client):
    """El contrato de refresco del cliente: /auth/stream-token devuelve `expires_in` y el JWT
    expira en el futuro cercano. Sin esto el margen de 60 s con que el reproductor renueva antes
    de caducar (api/stream.ts) no tendría base: `expira = Date.now() + expires_in*1000`."""
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.config import SECRET_KEY, ALGORITHM, STREAM_TOKEN_EXPIRE_MINUTES

    client.post("/auth/register", json={"email": "pf3@t.com", "password": "clave-larga-1"})
    access = client.post("/auth/login", data={"username": "pf3@t.com",
                                              "password": "clave-larga-1"}).json()["access_token"]

    r = client.post("/auth/stream-token",
                    headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["expires_in"] == STREAM_TOKEN_EXPIRE_MINUTES * 60, body
    assert body["expires_in"] > 60, "el margen de refresco (60s) no tendría sentido"

    claims = jwt.decode(body["token"], SECRET_KEY, algorithms=[ALGORITHM])
    assert claims["scope"] == "stream", claims

    now = datetime.now(timezone.utc)
    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    esperado = now + timedelta(seconds=body["expires_in"])
    # `exp` debe estar en el futuro y a ~expires_in de ahora (tolerancia de unos segundos).
    assert exp > now, claims
    assert abs((exp - esperado).total_seconds()) < 30, (exp, esperado)


def test_stream_range_invalido_416(client):  # B3
    """Rango insatisfacible (más allá del tamaño) o malformado → 416, y `bytes=100-` abierto → 206."""
    import os
    from app.database import SessionLocal
    from app import models
    music = os.environ["MUSIC_ROOT"]
    d = os.path.join(music, "catalogada", "Range416")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, "tema.mp3")
    with open(fp, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" + b"\x00" * 8192)   # ~8 KB
    size = os.path.getsize(fp)
    try:
        db = SessionLocal()
        tr = models.Track(title="R416", artist="A", file_path=fp, status="descargada", source="test")
        db.add(tr)
        db.commit()
        db.refresh(tr)
        tid = tr.id
        db.close()

        client.post("/auth/register", json={"email": "pf4@t.com", "password": "clave-larga-1"})
        access = client.post("/auth/login", data={"username": "pf4@t.com",
                                                  "password": "clave-larga-1"}).json()["access_token"]
        st = client.post("/auth/stream-token",
                         headers={"Authorization": f"Bearer {access}"}).json()["token"]
        origin = {"Origin": "http://localhost:3000"}

        # rango que empieza más allá del tamaño → 416
        bad = client.get(f"/stream/{tid}?t={st}", headers={**origin, "Range": f"bytes={size + 100}-"})
        assert bad.status_code == 416, bad.status_code

        # rango abierto por la derecha → 206 (el servidor corta en el tamaño)
        open_r = client.get(f"/stream/{tid}?t={st}", headers={**origin, "Range": "bytes=100-"})
        assert open_r.status_code == 206, open_r.status_code
        assert open_r.headers.get("content-range", "").startswith(f"bytes 100-{size - 1}/")
    finally:
        if os.path.exists(fp):
            os.unlink(fp)
