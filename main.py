from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import os, shutil, subprocess, uuid

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = "/tmp"

app = FastAPI(title="KMZ Processor")

# CORS robusto: permite todos los métodos y expone Content-Disposition
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # o limita a https://alvaromartinezg.github.io
    allow_credentials=False,
    allow_methods=["*"],          # 👈 evita 405 en preflight por métodos faltantes
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

# Respuesta explícita al preflight si algún proxy ignora el middleware
@app.options("/{path:path}")
def options_catch_all(path: str):
    return Response(status_code=204)

def _find_base_kmz() -> str:
    for name in ["DATABASE.kmz", "Database.kmz", "Transmission Network.kmz"]:
        p = os.path.join(APP_DIR, name)
        if os.path.exists(p):
            return p
    listing = ", ".join(sorted(os.listdir(APP_DIR)))
    raise HTTPException(500, f"No se encontró KMZ base. En app/: {listing}")

@app.post("/process")
async def process_kmz(test_kmz: UploadFile = File(None), file: UploadFile = File(None)):
    f = test_kmz or file
    if not f:
        raise HTTPException(400, "Esperaba archivo 'test_kmz' o 'file'.")

    name = (f.filename or "").lower()
    if not (name.endswith(".kmz") or name.endswith(".kml")):
        raise HTTPException(400, "Sube un .kmz o .kml válido.")

    # limpia /tmp
    for n in ("TEST.kmz","TEST.kml","Transmission Network.kmz","Exportado.kmz","informative-letters-v3.py"):
        p = os.path.join(TMP_DIR, n)
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    # guarda TEST.*
    test_dest = os.path.join(TMP_DIR, "TEST.kmz" if name.endswith(".kmz") else "TEST.kml")
    with open(test_dest, "wb") as out:
        out.write(await f.read())

    # prepara insumos
    base_src = _find_base_kmz()
    shutil.copyfile(base_src, os.path.join(TMP_DIR, "Transmission Network.kmz"))

    src_script = os.path.join(APP_DIR, "informative-letters-v3.py")
    if not os.path.exists(src_script):
        raise HTTPException(500, "Falta informative-letters-v3.py")
    shutil.copyfile(src_script, os.path.join(TMP_DIR, "informative-letters-v3.py"))

    # ejecuta
    try:
        subprocess.run(
            ["python3", "informative-letters-v3.py"],
            cwd=TMP_DIR, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Error al procesar:\n{(e.stderr or e.stdout or '').strip()}")

    out_path = os.path.join(TMP_DIR, "Exportado.kmz")
    if not os.path.exists(out_path):
        raise HTTPException(500, "No se generó Exportado.kmz")

    return FileResponse(
        out_path,
        media_type="application/vnd.google-earth.kmz",
        filename=f"Exportado_{uuid.uuid4().hex[:6]}.kmz",
    )
