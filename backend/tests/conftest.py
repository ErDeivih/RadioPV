import os, sys, tempfile, pytest
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
# Root del proyecto (para importar radiov.* y librosa-pipelines si hacen falta)
_ROOT = os.path.dirname(_BACKEND)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# El root tiene app.py (Streamlit); el paquete real es backend/app. Evita la sombra.
sys.modules.pop("app", None)
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mkstemp(suffix=".db")[1].replace("\\", "/")
os.environ.setdefault("RADIOPV_ENV", "dev")

# MUSIC_ROOT temporal para poder probar /stream con ficheros dentro de la raíz de música.
# Se coloca dentro del workspace (zona escribible) para no chocar con el sandbox.
_MUSIC = os.path.join(_BACKEND, "..", "_test_music")
os.makedirs(_MUSIC, exist_ok=True)
os.environ["MUSIC_ROOT"] = _MUSIC.replace("\\", "/")

# MEDIA_ROOT temporal para poder probar /media/covers y /media/artists
_MEDIA = os.path.join(_BACKEND, "..", "_test_media")
os.makedirs(_MEDIA, exist_ok=True)
os.environ["MEDIA_ROOT"] = _MEDIA.replace("\\", "/")

from fastapi.testclient import TestClient          # noqa: E402
from app.main import app                            # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/auth/register", json={"email": "t@t.com", "password": "clave-larga-1",
                                            "display_name": "T"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]
