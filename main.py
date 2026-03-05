"""
Punto de entrada principal del Waitry Stock Reporter.
Ejecuta scraping → genera PDF → envía por email.
"""

import os
import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Forzar flush inmediato en stdout para que Railway capture los logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from scraper import scrape_waitry
from report_generator import generate_pdf
from email_sender import send_report

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
    place_name   = os.getenv("PLACE_NAME", "Mi Cafetería")
    recipients   = os.getenv("EMAIL_RECIPIENTS", "").split(",")
    recipients   = [r.strip() for r in recipients if r.strip()]
    demo_mode    = os.getenv("DEMO_MODE", "false").lower() == "true"

    # Validaciones
    if not demo_mode:
        if not waitry_user or not waitry_pass:
            log.error("Faltan variables WAITRY_USER y/o WAITRY_PASSWORD.")
            sys.exit(1)
        if not recipients:
            log.error("Falta variable EMAIL_RECIPIENTS.")
            sys.exit(1)

    now = datetime.now()
    output_path = f"/tmp/reporte_stock_{now.strftime('%Y%m%d_%H%M')}.pdf"

    # ── 1. Scraping ───────────────────────────────────────────────────────
    if demo_mode:
        log.info("Modo DEMO activo — usando datos de ejemplo.")
        products = []  # report_generator usará datos demo internamente
    else:
        log.info("Iniciando scraping de Waitry...")
        products = scrape_waitry(waitry_user, waitry_pass, headless=True)
        log.info(f"Productos obtenidos: {len(products)}")

    # ── 2. Generar PDF ────────────────────────────────────────────────────
    log.info(f"Generando reporte PDF en: {output_path}")
    generate_pdf(
        products_raw=products,
        output_path=output_path,
        place_name=place_name,
        report_date=now,
    )
    log.info("PDF generado correctamente.")

    # ── 3. Enviar por email ───────────────────────────────────────────────
    if demo_mode:
        log.info(f"Modo DEMO — email no enviado. PDF disponible en: {output_path}")
    else:
        log.info(f"Enviando reporte a: {', '.join(recipients)}")
        success = send_report(
            pdf_path=output_path,
            recipients=recipients,
            place_name=place_name,
            report_date=now,
        )
        if success:
            log.info("✅ Reporte enviado con éxito.")
        else:
            log.error("❌ Hubo un error al enviar el email.")
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
