# app/main.py
import os, shutil, subprocess, uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = "/tmp"  # Cloud Run: carpeta escribible

app = FastAPI(title="KMZ Processor")

# CORS robusto + exponer Content-Disposition (para nombre de descarga)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],                 # si quieres, restringe a tu GitHub Pages
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

# Handler explícito para preflight: evita 405 si algún proxy no respeta el middleware
@app.options("/process")
def options_process():
    return Response(status_code=204)

def _find_base_kmz() -> str:
    """
    Busca el KMZ base dentro del contenedor respetando mayúsculas/minúsculas.
    En tus mensajes anteriores el archivo subido se llama 'DATABASE.kmz'.
    """
    candidates = ["DATABASE.kmz", "Database.kmz", "Transmission Network.kmz"]
    for name in candidates:
        p = os.path.join(APP_DIR, name)
        if os.path.exists(p):
            return p
    # mensaje de depuración con listado
    listing = ", ".join(sorted(os.listdir(APP_DIR)))
    raise HTTPException(
        status_code=500,
        detail=f"No se encontró el KMZ base (probé {candidates}). Archivos en app/: {listing}"
    )

@app.post("/process")
async def process(
    test_kmz: UploadFile | None = File(default=None),  # front nuevo
    file: UploadFile | None = File(default=None),      # front antiguo/otros
):
    f = test_kmz or file
    if f is None:
        raise HTTPException(status_code=400, detail="Esperaba archivo en 'test_kmz' o 'file'.")

    filename = (f.filename or "").lower()
    if not (filename.endswith(".kmz") or filename.endswith(".kml")):
        raise HTTPException(status_code=400, detail="Sube un archivo .kmz o .kml válido.")

    # Limpia /tmp
    for name in ("TEST.kmz", "TEST.kml", "Transmission Network.kmz", "Exportado.kmz", "informative-letters-v3.py"):
        p = os.path.join(TMP_DIR, name)
        try:
            if os.path.exists(p):
                os.remove(p)
        except:
            pass

    # Guarda TEST.* en /tmp
    test_dest = os.path.join(TMP_DIR, "TEST.kmz" if filename.endswith(".kmz") else "TEST.kml")
    with open(test_dest, "wb") as out:
        out.write(await f.read())

    # Copia BASE y script a /tmp
    base_src = _find_base_kmz()  # ← respeta el nombre real (DATABASE.kmz)
    base_dest = os.path.join(TMP_DIR, "Transmission Network.kmz")  # nombre que espera tu script
    shutil.copyfile(base_src, base_dest)

    script_src = os.path.join(APP_DIR, "informative-letters-v3.py")
    if not os.path.exists(script_src):
        raise HTTPException(status_code=500, detail="Falta informative-letters-v3.py en el contenedor")
    shutil.copyfile(script_src, os.path.join(TMP_DIR, "informative-letters-v3.py"))

    # Ejecuta el script en /tmp (debe producir Exportado.kmz)
    try:
        res = subprocess.run(
            ["python3", "informative-letters-v3.py"],
            cwd=TMP_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        logs = (e.stderr or e.stdout or "").strip()
        raise HTTPException(status_code=500, detail=f"Error al procesar:\n{logs}")

    out_path = os.path.join(TMP_DIR, "Exportado.kmz")
    if not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="No se generó Exportado.kmz")

    download_name = f"Exportado_{uuid.uuid4().hex[:6]}.kmz"
    return FileResponse(
        out_path,
        media_type="application/vnd.google-earth.kmz",
        filename=download_name,
    )
