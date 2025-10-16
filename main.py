# main.py (raíz)
import os, shutil, subprocess, uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware

APP_DIR = os.path.dirname(os.path.abspath(__file__))  # ← raíz del repo dentro del contenedor
TMP_DIR = "/tmp"  # Cloud Run: carpeta escribible

app = FastAPI(title="KMZ Processor")

# CORS robusto: acepta preflight de cualquier método y expone Content-Disposition
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],              # o limita a tu GitHub Pages
    allow_credentials=False,
    allow_methods=["*"],              # evita 405 en OPTIONS
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

# --- nuevo: buscador de base canalizada
def _find_canalizado_kmz() -> str | None:
    for name in ["Database_Canalizado.kmz", "DATABASE_CANALIZADO.kmz", "Transmission Network Canalizado.kmz"]:
        p = os.path.join(APP_DIR, name)
        if os.path.exists(p):
            return p
    return None

# Respuesta explícita para cualquier OPTIONS (por si un proxy ignora el middleware)
@app.options("/{path:path}")
def options_any(path: str):
    return Response(status_code=204)

def _find_base_kmz() -> str:
    # En tu repo el nombre es exactamente 'Database.kmz'
    candidates = ["Database.kmz", "DATABASE.kmz", "Transmission Network.kmz"]
    for name in candidates:
        p = os.path.join(APP_DIR, name)
        if os.path.exists(p):
            return p
    listing = ", ".join(sorted(os.listdir(APP_DIR)))
    raise HTTPException(500, f"No se encontró el KMZ base. Archivos en raíz: {listing}")

@app.post("/process")
async def process_kmz(test_kmz: UploadFile = File(None), file: UploadFile = File(None)):
    # Acepta ambos nombres de campo (tu web nueva usa 'test_kmz'; otras podrían usar 'file')
    f = test_kmz or file
    if not f:
        raise HTTPException(400, "Esperaba archivo en 'test_kmz' o 'file'.")

    name = (f.filename or "").lower()
    if not (name.endswith(".kmz") or name.endswith(".kml")):
        raise HTTPException(400, "Sube un .kmz o .kml válido.")

    # Limpia /tmp
    for n in ("TEST.kmz","TEST.kml","Transmission Network.kmz","Exportado.kmz","informative-letters-v3.py"):
        p = os.path.join(TMP_DIR, n)
        try:
            if os.path.exists(p):
                os.remove(p)
        except:
            pass

    # Guarda TEST.* en /tmp
    test_dest = os.path.join(TMP_DIR, "TEST.kmz" if name.endswith(".kmz") else "TEST.kml")
    with open(test_dest, "wb") as out:
        out.write(await f.read())

    # Copia insumos desde la RAÍZ del contenedor
    base_src = _find_base_kmz()  # ← 'Database.kmz' en tu repo
    shutil.copyfile(base_src, os.path.join(TMP_DIR, "Transmission Network.kmz"))
    # Copia opcional de la base CANALIZADA
    base_can_src = _find_canalizado_kmz()
    if base_can_src:
        shutil.copyfile(base_can_src, os.path.join(TMP_DIR, "Transmission Network Canalizado.kmz"))


    script_src = os.path.join(APP_DIR, "informative-letters-v3.py")
    if not os.path.exists(script_src):
        raise HTTPException(500, "Falta informative-letters-v3.py en el contenedor")
    shutil.copyfile(script_src, os.path.join(TMP_DIR, "informative-letters-v3.py"))

    # Ejecuta el script (debe generar Exportado.kmz en /tmp)
    try:
        subprocess.run(
            ["python3", "informative-letters-v3.py"],
            cwd=TMP_DIR, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        logs = (e.stderr or e.stdout or "").strip()
        raise HTTPException(500, f"Error al procesar:\n{logs}")

    out_path = os.path.join(TMP_DIR, "Exportado.kmz")
    if not os.path.exists(out_path):
        raise HTTPException(500, "No se generó Exportado.kmz")

    return FileResponse(
        out_path,
        media_type="application/vnd.google-earth.kmz",
        filename=f"Exportado_{uuid.uuid4().hex[:6]}.kmz",
    )
