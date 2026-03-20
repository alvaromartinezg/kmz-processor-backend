# main.py (raíz)
import os
import shutil
import subprocess
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = "/tmp"

app = FastAPI(title="KMZ Processor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

@app.options("/{path:path}")
def options_any(path: str):
    return Response(status_code=204)

def _find_base_kmz() -> str | None:
    candidates = ["Database.kmz", "DATABASE.kmz", "Transmission Network.kmz"]
    for name in candidates:
        p = os.path.join(APP_DIR, name)
        if os.path.exists(p):
            return p
    return None

def _find_canalizado_kmz() -> str | None:
    candidates = [
        "Database_Canalizado.kmz",
        "DATABASE_CANALIZADO.kmz",
        "Transmission Network Canalizado.kmz",
    ]
    for name in candidates:
        p = os.path.join(APP_DIR, name)
        if os.path.exists(p):
            return p
    return None

@app.post("/process")
async def process_kmz(
    test_kmz: UploadFile = File(None),
    file: UploadFile = File(None),
    mode: str = Form("both"),
):
    f = test_kmz or file
    if not f:
        raise HTTPException(400, "Esperaba archivo en 'test_kmz' o 'file'.")

    name = (f.filename or "").lower()
    if not (name.endswith(".kmz") or name.endswith(".kml")):
        raise HTTPException(400, "Sube un .kmz o .kml válido.")

    for n in (
        "TEST.kmz",
        "TEST.kml",
        "Transmission Network.kmz",
        "Transmission Network Canalizado.kmz",
        "Exportado.kmz",
        "informative-letters-v3.py",
    ):
        p = os.path.join(TMP_DIR, n)
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    test_dest = os.path.join(TMP_DIR, "TEST.kmz" if name.endswith(".kmz") else "TEST.kml")
    with open(test_dest, "wb") as out:
        out.write(await f.read())

    mode = (mode or "both").strip().lower()
    if mode not in {"both", "general", "canalizado"}:
        raise HTTPException(400, f"Modo inválido: {mode}")

    base_src = _find_base_kmz()
    base_can_src = _find_canalizado_kmz()

    if mode == "both":
        if not base_src and not base_can_src:
            listing = ", ".join(sorted(os.listdir(APP_DIR)))
            raise HTTPException(500, f"No se encontró ninguna base KMZ en el contenedor. Archivos en raíz: {listing}")

        if base_src:
            shutil.copyfile(base_src, os.path.join(TMP_DIR, "Transmission Network.kmz"))

        if base_can_src:
            shutil.copyfile(base_can_src, os.path.join(TMP_DIR, "Transmission Network Canalizado.kmz"))

    elif mode == "general":
        if not base_src:
            listing = ", ".join(sorted(os.listdir(APP_DIR)))
            raise HTTPException(500, f"No se encontró la base general (aérea). Archivos en raíz: {listing}")

        shutil.copyfile(base_src, os.path.join(TMP_DIR, "Transmission Network.kmz"))

    elif mode == "canalizado":
        if not base_can_src:
            listing = ", ".join(sorted(os.listdir(APP_DIR)))
            raise HTTPException(500, f"No se encontró la base canalizada. Archivos en raíz: {listing}")

        shutil.copyfile(base_can_src, os.path.join(TMP_DIR, "Transmission Network.kmz"))

    script_src = os.path.join(APP_DIR, "informative-letters-v3.py")
    if not os.path.exists(script_src):
        raise HTTPException(500, "Falta informative-letters-v3.py en el contenedor")

    shutil.copyfile(script_src, os.path.join(TMP_DIR, "informative-letters-v3.py"))

    try:
        result = subprocess.run(
            ["python3", "informative-letters-v3.py"],
            cwd=TMP_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as e:
        raise HTTPException(500, f"Error al ejecutar el script: {e}")

    logs = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()

    if result.returncode == 2 or "[EMPTY]" in logs:
        return Response(status_code=204)

    if result.returncode != 0:
        raise HTTPException(500, f"Error al procesar:\n{logs}")

    out_path = os.path.join(TMP_DIR, "Exportado.kmz")
    if not os.path.exists(out_path):
        raise HTTPException(500, "No se generó Exportado.kmz")

    return FileResponse(
        out_path,
        media_type="application/vnd.google-earth.kmz",
        filename=f"Exportado_{uuid.uuid4().hex[:6]}.kmz",
    )
