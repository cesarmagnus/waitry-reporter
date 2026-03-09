"""
Punto de entrada principal del Waitry Stock Reporter.
Ejecuta scraping → genera PDF → envía por email.
"""

import os
import sys
import logging
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Forzar flush inmediato en stdout para que Railway capture los logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from scraper import scrape_all_places
from report_generator import generate_pdf
from whatsapp_sender import send_whatsapp_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


def main():
    log.info("=" * 50)
    log.info("  Waitry Stock Reporter — Iniciando")
    log.info("=" * 50)

    # ── Configuración desde variables de entorno ──────────────────────────
    waitry_user  = os.getenv("WAITRY_USER")
    waitry_pass  = os.getenv("WAITRY_PASSWORD")
    place_name_global = os.getenv("PLACE_NAME", "Mi Cafetería")
    demo_mode    = os.getenv("DEMO_MODE", "false").lower() == "true"
    categoria_filtro = os.getenv("CATEGORIA_FILTRO", "").strip() or None

    # Validaciones
    if not demo_mode:
        if not waitry_user or not waitry_pass:
            log.error("Faltan variables WAITRY_USER y/o WAITRY_PASSWORD.")
            sys.exit(1)

    TZ_CHILE = timezone(timedelta(hours=-3))
    now = datetime.now(tz=TZ_CHILE)
    output_path = f"/tmp/reporte_stock_{now.strftime('%Y%m%d_%H%M')}.pdf"

    # ── 1. Scraping de todas las sucursales ───────────────────────────────
    if demo_mode:
        log.info("Modo DEMO activo — usando datos de ejemplo.")
        places_data = [{"place_name": "Sucursal Demo", "products": []}]
    else:
        log.info("Iniciando scraping de Waitry...")
        places_data = scrape_all_places(waitry_user, waitry_pass, headless=True)
        log.info(f"Sucursales procesadas: {len(places_data)}")

    # ── 2. Generar un PDF por sucursal ────────────────────────────────────
    pdf_paths = []
    for place in places_data:
        place_name = place["place_name"]
        products   = place["products"]
        safe_name  = place_name.replace(" ", "_").replace("/", "-")
        pdf_path   = f"/tmp/reporte_stock_{safe_name}_{now.strftime('%Y%m%d_%H%M')}.pdf"

        log.info(f"Generando PDF para '{place_name}' ({len(products)} productos)...")
        generate_pdf(
            products_raw=products,
            output_path=pdf_path,
            place_name=f"{place_name}",
            report_date=now,
            categoria_filtro=categoria_filtro,
        )
        pdf_paths.append((place_name, pdf_path))
        log.info(f"PDF generado: {pdf_path}")

    # ── 3. Enviar por WhatsApp ────────────────────────────────────────────
    if demo_mode:
        log.info(f"Modo DEMO — PDFs generados: {[p for _, p in pdf_paths]}")
    else:
        log.info("Enviando reporte por WhatsApp...")
        wa_success = send_whatsapp_report(
            pdf_paths=pdf_paths,
            place_name=place_name_global,
            report_date=now,
        )
        if wa_success:
            log.info("✅ WhatsApp enviado con éxito.")
        else:
            log.error("❌ Hubo un error al enviar por WhatsApp.")
            sys.exit(1)

    log.info("=" * 50)
    log.info("  Proceso completado.")
    log.info("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error(f"Error fatal: {e}")
        log.error(traceback.format_exc())
        sys.exit(1)
