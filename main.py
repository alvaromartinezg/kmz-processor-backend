# main.py
import os, shutil, subprocess, uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = "/tmp"  # Cloud Run: carpeta escribible

app = FastAPI(title="KMZ Processor")

# CORS: deja * por simplicidad. Luego puedes restringir a https://TU_USUARIO.github.io
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS", "GET"],
    allow_headers=["*"],
)

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

@app.post("/process")
async def process(test_kmz: UploadFile = File(...)):
    # Validación simple de extensión
    filename = test_kmz.filename or ""
    if not (filename.lower().endswith(".kmz") or filename.lower().endswith(".kml")):
        raise HTTPException(status_code=400, detail="Sube un archivo .kmz o .kml válido")

    # Limpia /tmp
    for f in ("TEST.kmz", "TEST.kml", "DATABASE.kmz", "Exportado.kmz", "informative-letters-v3.py"):
        p = os.path.join(TMP_DIR, f)
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    # Guarda TEST (kmz/kml) en /tmp
    test_dest = os.path.join(TMP_DIR, "TEST.kmz" if filename.lower().endswith(".kmz") else "TEST.kml")
    with open(test_dest, "wb") as f:
        f.write(await test_kmz.read())

    # Copia BASE y script a /tmp
    base_src = os.path.join(APP_DIR, "DATABASE.kmz")
    if not os.path.exists(base_src):
        raise HTTPException(status_code=500, detail="DATABASE.kmz no está en el contenedor")
    shutil.copyfile(base_src, os.path.join(TMP_DIR, "DATABASE.kmz"))

    script_src = os.path.join(APP_DIR, "informative-letters-v3.py")
    if not os.path.exists(script_src):
        raise HTTPException(status_code=500, detail="Falta informative-letters-v3.py en el contenedor")
    shutil.copyfile(script_src, os.path.join(TMP_DIR, "informative-letters-v3.py"))

    # Ejecuta el script DESDE /tmp para que escriba Exportado.kmz ahí
    try:
        subprocess.run(
            ["python3", "informative-letters-v3.py"],
            cwd=TMP_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        # Devuelve logs del script para depurar
        raise HTTPException(status_code=500, detail=f"Error al procesar: {e.stderr or e.stdout}")

    out_path = os.path.join(TMP_DIR, "Exportado.kmz")
    if not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="No se generó Exportado.kmz")

    # Nombre amigable de descarga
    download_name = f"Exportado_{uuid.uuid4().hex[:6]}.kmz"
    return FileResponse(
        out_path,
        media_type="application/vnd.google-earth.kmz",
        filename=download_name,
    )
