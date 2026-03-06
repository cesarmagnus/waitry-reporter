"""
Waitry Stock Scraper
Hace login en app.waitry.net, navega a Productos → Stock,
usa el botón Exportar para descargar el CSV y retorna los datos.
"""

import os
import csv
import io
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def login(page, username: str, password: str) -> bool:
    """Inicia sesión en Waitry. Retorna True si fue exitoso."""
    log.info("Navegando al login de Waitry...")
    page.goto("https://app.waitry.net/", wait_until="networkidle", timeout=30000)

    # Esperar extra para que Angular termine de renderizar
    page.wait_for_timeout(3000)

    log.info(f"URL actual: {page.url}")
    log.info(f"Título de página: {page.title()}")

    page.wait_for_selector(
        "input[type='email'], input[name='email'], input[name='username'], input[type='text']",
        timeout=30000
    )

    page.locator("input[type='email'], input[name='email'], input[name='username'], input[type='text']").first.fill(username)
    page.locator("input[type='password']").first.fill(password)
    page.locator("button[type='submit'], button:has-text('Ingresar'), button:has-text('Login'), button:has-text('Entrar')").first.click()

    try:
        page.wait_for_url(lambda url: "login" not in url.lower(), timeout=30000)
        log.info("Login exitoso.")
        return True
    except PlaywrightTimeout:
        log.error(f"Falló el login. URL actual: {page.url}")
        log.error(f"Contenido visible: {page.content()[:500]}")
        return False


def navigate_to_stock(page) -> bool:
    """
    Navega por el menú de Waitry:
    1. Clic en 'Productos' en el menú lateral
    2. Clic en los tres puntos (menú contextual, clase ng-scope)
    3. Clic en la opción 'Stock'
    """
    log.info("Navegando a Productos...")

    # ── Paso 1: clic en "Productos" en el menú lateral ────────────────────
    try:
        # Esperar más tiempo para que Angular cargue el menú
        page.wait_for_timeout(8000)

        # En modo debug, loguear HTML completo para inspeccionar estructura
        if os.getenv("DEBUG_MODE") == "true":
            html = page.content()
            # Buscar específicamente la parte del menú lateral
            import re
            # Extraer fragmento relevante buscando palabras clave del menú
            for keyword in ["Productos", "sidebar", "nav", "menu"]:
                idx = html.find(keyword)
                if idx != -1:
                    log.info(f"=== Encontrado '{keyword}' en posición {idx} ===")
                    log.info(f"Contexto: {html[max(0,idx-200):idx+500]}")
                    break
            else:
                log.info(f"=== HTML (chars 3000-6000) ===\n{html[3000:6000]}")

        productos_link = page.locator(
            "md-list-item:has(p.ng-scope:text-is('Productos')), "
            "md-list-item:has(p:text-is('Productos'))"
        ).first
        productos_link.wait_for(state="visible", timeout=10000)
        productos_link.click()
        page.wait_for_load_state("networkidle")
        log.info("Clic en 'Productos' exitoso.")
    except Exception as e:
        log.error(f"No se encontró el menú 'Productos': {e}")
        return False

    # ── Paso 2: clic en los tres puntos (ng-scope) ────────────────────────
    log.info("Buscando menú de tres puntos...")
    try:
        tres_puntos = page.locator(
            "md-list-item:has(p.ng-scope:text-is('Productos')) button, "
            "md-list-item:has(p:text-is('Productos')) .md-secondary-container button, "
            "md-list-item:has(p:text-is('Productos')) md-button"
        ).first
        tres_puntos.wait_for(state="visible", timeout=8000)
        tres_puntos.click()
        log.info("Clic en tres puntos exitoso.")
    except Exception:
        log.warning("Selector principal falló, intentando hover para revelar tres puntos...")
        try:
            item = page.locator("md-list-item:has(p.ng-scope:text-is('Productos'))").first
            item.hover()
            page.wait_for_timeout(1000)
            tres_puntos = page.locator(
                "md-list-item:has(p:text-is('Productos')) button, "
                "[class*='dropdown-toggle'], "
                "[data-toggle='dropdown']"
            ).first
            tres_puntos.click()
        except Exception as e2:
            log.error(f"No se pudo encontrar el menú de tres puntos: {e2}")
            return False

    # ── Paso 3: clic en "Stock" en el dropdown ────────────────────────────
    log.info("Buscando opción 'Stock' en el menú desplegable...")
    try:
        page.wait_for_timeout(1000)  # Esperar que el overlay de Angular Material aparezca

        # Buscar todos los botones menuitem y hacer clic en el que dice "Stock"
        clicked = page.evaluate("""
            () => {
                const buttons = document.querySelectorAll('button[role="menuitem"]');
                for (const btn of buttons) {
                    if (btn.textContent.trim().includes('Stock')) {
                        btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                        return btn.textContent.trim();
                    }
                }
                // También buscar en el overlay de Angular Material
                const allElements = document.querySelectorAll('[role="menuitem"], .md-menu-item button, md-menu-content button');
                for (const el of allElements) {
                    if (el.textContent.trim().includes('Stock')) {
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                        return 'found via overlay: ' + el.textContent.trim();
                    }
                }
                return null;
            }
        """)

        if clicked:
            log.info(f"Clic en Stock via JS exitoso: {clicked}")
            page.wait_for_load_state("networkidle")
            log.info("Navegué a la sección Stock exitosamente.")
            return True
        else:
            log.error("No se encontró el botón Stock en el DOM.")
            return False

    except Exception as e:
        log.error(f"Error al hacer clic en Stock: {e}")
        return False


def export_and_parse(page) -> list[dict]:
    """
    Hace clic en 'Exportar', captura el archivo descargado
    y retorna los datos como lista de dicts.
    """
    log.info("Buscando botón 'Exportar'...")
    try:
        export_btn = page.locator(
            "button:has-text('Exportar'), "
            "a:has-text('Exportar'), "
            "[class*='export']:has-text('Exportar')"
        ).first
        export_btn.wait_for(state="visible", timeout=10000)

        with page.expect_download(timeout=20000) as download_info:
            export_btn.click()

        download = download_info.value
        log.info(f"Archivo descargado: {download.suggested_filename}")
        filepath = download.path()
        filename = download.suggested_filename.lower()

        if filename.endswith(".csv"):
            return _parse_csv(filepath)
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            return _parse_excel(filepath)
        else:
            log.warning(f"Formato desconocido ({filename}), intentando como CSV...")
            return _parse_csv(filepath)

    except PlaywrightTimeout:
        log.warning("No se pudo usar el botón Exportar. Leyendo tabla directamente...")
        return _extract_table_fallback(page)
    except Exception as e:
        log.error(f"Error al exportar: {e}")
        return _extract_table_fallback(page)


def _parse_csv(filepath: str) -> list[dict]:
    """Parsea un archivo CSV descargado."""
    products = []
    for encoding in ["utf-8-sig", "latin-1"]:
        try:
            with open(filepath, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    products.append(dict(row))
            log.info(f"CSV parseado: {len(products)} productos.")
            return products
        except UnicodeDecodeError:
            continue
        except Exception as e:
            log.error(f"Error parseando CSV: {e}")
            return []
    return products


def _parse_excel(filepath: str) -> list[dict]:
    """Parsea un archivo Excel descargado, detectando el formato real."""
    # Leer los primeros bytes para detectar el formato real
    with open(filepath, "rb") as f:
        header = f.read(8)

    # Magic bytes: ZIP = xlsx, D0CF = xls antiguo, texto = CSV
    is_xlsx = header[:4] == b'PK\x03\x04'
    is_xls  = header[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'

    if is_xlsx:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return []
            headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]
            products = []
            for row in rows[1:]:
                if any(cell is not None for cell in row):
                    products.append(dict(zip(headers, [str(v).strip() if v is not None else "" for v in row])))
            log.info(f"Excel (xlsx) parseado: {len(products)} productos.")
            return products
        except Exception as e:
            log.error(f"Error parseando xlsx: {e}")
            return []

    elif is_xls:
        try:
            import xlrd
            wb = xlrd.open_workbook(filepath)
            ws = wb.sheet_by_index(0)
            headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
            products = []
            for r in range(1, ws.nrows):
                row = [str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)]
                if any(row):
                    products.append(dict(zip(headers, row)))
            log.info(f"Excel (xls) parseado: {len(products)} productos.")
            return products
        except ImportError:
            log.warning("xlrd no instalado, intentando como CSV...")
            return _parse_csv(filepath)
        except Exception as e:
            log.error(f"Error parseando xls: {e}")
            return []

    else:
        # Probablemente es un CSV con extensión xlsx
        log.warning("Archivo no es Excel válido, intentando como CSV...")
        return _parse_csv(filepath)


def _extract_table_fallback(page) -> list[dict]:
    """Fallback: extrae la tabla HTML directamente si el export falla."""
    log.info("Extrayendo tabla HTML como fallback...")
    products = []
    try:
        page.wait_for_selector("table", timeout=8000)
        headers = [th.inner_text().strip() for th in page.locator("table thead th").all()]
        rows = page.locator("table tbody tr").all()
        for row in rows:
            cells = [td.inner_text().strip() for td in row.locator("td").all()]
            if cells and any(c for c in cells):
                if headers and len(cells) == len(headers):
                    products.append(dict(zip(headers, cells)))
                else:
                    products.append({f"col_{i}": v for i, v in enumerate(cells)})
        log.info(f"Tabla HTML extraída: {len(products)} productos.")
    except Exception as e:
        log.error(f"Fallback también falló: {e}")
    return products


def scrape_waitry(username: str, password: str, headless: bool = True) -> list[dict]:
    """Función principal. Retorna lista de productos con stock."""
    with sync_playwright() as pw:
        log.info("Iniciando Chromium...")
        browser = pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        log.info("Chromium iniciado correctamente.")
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            accept_downloads=True,
        )
        page = context.new_page()

        try:
            if not login(page, username, password):
                return []

            if not navigate_to_stock(page):
                log.warning("No se pudo navegar al stock. Intentando extracción de emergencia...")
                return _extract_table_fallback(page)

            return export_and_parse(page)

        except Exception as e:
            log.error(f"Error durante el scraping: {e}")
            try:
                page.screenshot(path="/tmp/waitry_error.png")
                log.info("Screenshot de error guardado en /tmp/waitry_error.png")
            except Exception:
                pass
            return []

        finally:
            browser.close()
