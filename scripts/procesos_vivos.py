"""¿Está corriendo el análisis? Sin `ps` en la imagen, se mira /proc directamente."""
import os

vivos = []
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            linea = f.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    except OSError:
        continue
    if linea:
        vivos.append(linea)

analisis = [v for v in vivos if "analisis_completo" in v]
ffmpeg = [v for v in vivos if "ffmpeg" in v]
print(f"procesos con cmdline visible: {len(vivos)}")
print(f"  analisis_completo: {len(analisis)}")
for a in analisis[:3]:
    print("   ", a[:110])
print(f"  ffmpeg: {len(ffmpeg)}")
for f in ffmpeg[:3]:
    print("   ", f[:110])
