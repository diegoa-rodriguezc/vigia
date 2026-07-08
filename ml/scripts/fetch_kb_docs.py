# Verificación de INTEGRIDAD (y re-obtención) de los documentos de la base de conocimiento
# del RAG (data/kb_docs/).
#
# El PDF de la *Política de Seguridad, Defensa y Convivencia Ciudadana 2022-2026* (~47 MB,
# Ministerio de Defensa / Policía Nacional) se versiona en el repositorio como copia íntegra
# con cita (reproducción de textos oficiales, art. 41 de la Ley 23 de 1982). Este script
# comprueba que la copia local coincide con el original oficial (SHA-256 y tamaño exacto) y,
# si faltara o no coincidiera, la re-obtiene del sitio oficial. Si el archivo ya existe y su
# hash coincide, no vuelve a descargarlo.
#
# Ejecución:
#   make kb-docs                                            # dentro del contenedor (recomendado)
#   docker compose exec -T ml python - < ml/scripts/fetch_kb_docs.py
#   python ml/scripts/fetch_kb_docs.py                      # en el host, desde la raíz del repo
#
# Comportamiento ante fallos — la copia local NUNCA se elimina ni se deja a medias (la
# descarga va a un temporal y solo reemplaza tras verificar):
#   - Hash de una descarga nueva que no coincide → error y código 1 (el documento cambió en
#     origen o la descarga se corrompió); el temporal se descarta y la copia local queda intacta.
#   - Sitio de origen caído o sin red → AVISO y código 0 (no bloquea `make deploy`): si hay
#     copia local queda tal cual (sin contrastar); si no la hay, el RAG opera sin el documento.
import hashlib
import sys
import urllib.request
from pathlib import Path

DOCS = [
    {
        "archivo": "Política de Seguridad Defensa y Convivencia Ciudadana.pdf",
        # [sic] la errata «Ciudadna» de la URL es del sitio oficial.
        "url": (
            "https://www.policia.gov.co/sites/default/files/2024-12/"
            "Pol%C3%ADtica%20de%20Seguridad%20Defensa%20y%20Convivencia%20Ciudadna.pdf"
        ),
        "sha256": "5b169a5a87ec7f9de57d7879ee4fa22fc83e9f288e1e0a903939a666b9f6af1a",
        "bytes": 47785152,
    },
]


def _docs_dir() -> Path:
    """Carpeta destino: settings del paquete si está instalado; ./data/kb_docs si no."""
    try:
        from vigia.config import settings

        return settings.rag_docs_dir
    except Exception:  # noqa: BLE001 — en el host puede no estar instalado el paquete
        return Path("data") / "kb_docs"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    dest_dir = _docs_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    fallos = 0
    for doc in DOCS:
        dest = dest_dir / doc["archivo"]
        if dest.exists() and _sha256(dest) == doc["sha256"]:
            print(f"OK (ya presente y verificado): {dest}")
            continue
        print(f"Descargando {doc['archivo']} ({doc['bytes'] / 1e6:.0f} MB)…", flush=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            urllib.request.urlretrieve(doc["url"], tmp)  # noqa: S310 — URL fija https oficial
        except OSError as exc:
            # Enlace caído o sin red: NUNCA se toca la copia local (si existe, queda tal
            # cual) y NO se aborta el despliegue — la copia versionada del repo es la fuente.
            tmp.unlink(missing_ok=True)
            situacion = (
                "no fue posible contrastarla con el original en línea; la copia local queda intacta"
                if dest.exists()
                else "no fue posible obtenerlo; el índice del RAG operará sin este documento"
            )
            print(
                f"AVISO: el sitio de origen de '{doc['archivo']}' no respondió ({exc}); "
                f"{situacion}.",
                file=sys.stderr,
            )
            continue
        real_hash, real_size = _sha256(tmp), tmp.stat().st_size
        if real_hash != doc["sha256"] or real_size != doc["bytes"]:
            tmp.unlink(missing_ok=True)
            print(
                f"ERROR: '{doc['archivo']}' no coincide con lo esperado "
                f"(sha256 {real_hash[:12]}… vs {doc['sha256'][:12]}…, "
                f"{real_size} vs {doc['bytes']} bytes). El documento pudo cambiar en origen; "
                "verificar la URL y actualizar el hash en ml/scripts/fetch_kb_docs.py.",
                file=sys.stderr,
            )
            fallos += 1
            continue
        tmp.replace(dest)
        print(f"OK (descargado y verificado): {dest}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
