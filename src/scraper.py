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
    Espera que la tabla de stock cargue y luego hace clic en 'Exportar'.
    """
    log.info("Esperando que carguen los datos de stock...")
    try:
        # Esperar a que aparezca al menos una fila de datos en la tabla
        page.wait_for_selector(
            "table tbody tr, "
            "[class*='row']:not(:empty), "
            "md-list-item[ng-repeat]",
            timeout=15000
        )
        log.info("Datos de stock cargados.")
    except PlaywrightTimeout:
        log.warning("Timeout esperando datos — intentando exportar igual...")

    # Espera adicional para asegurar que todos los datos están renderizados
    page.wait_for_timeout(6000)

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
        # Diagnóstico: ver qué hay adentro del ZIP
        try:
            import zipfile
            with zipfile.ZipFile(filepath) as z:
                log.info(f"Contenido del ZIP: {z.namelist()}")
        except Exception as ze:
            log.warning(f"No es un ZIP válido: {ze}")
            with open(filepath, "r", encoding="utf-8-sig", errors="ignore") as f:
                preview = f.read(500)
            log.info(f"Primeros 500 chars del archivo: {preview}")
            return _parse_csv(filepath)

        # Intentar con openpyxl primero
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
            log.warning(f"openpyxl falló ({e}), leyendo XML directamente...")

        # Fallback: leer sheet1.xml directamente del ZIP
        try:
            import zipfile
            import xml.etree.ElementTree as ET

            with zipfile.ZipFile(filepath) as z:
                # Log del contenido XML para debugging
                with z.open('xl/worksheets/sheet1.xml') as f:
                    raw_xml = f.read().decode('utf-8', errors='ignore')
                    log.info(f"=== sheet1.xml (primeros 1000 chars) ===\n{raw_xml[:1000]}")

                # Leer strings compartidos
                shared_strings = []
                if 'xl/sharedStrings.xml' in z.namelist():
                    with z.open('xl/sharedStrings.xml') as f:
                        raw_ss = f.read().decode('utf-8', errors='ignore')
                        log.info(f"=== sharedStrings.xml (primeros 500 chars) ===\n{raw_ss[:500]}")
                    with z.open('xl/sharedStrings.xml') as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        ns = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
                        for si in root.findall(f'.//{ns}si'):
                            texts = [t.text or '' for t in si.findall(f'.//{ns}t')]
                            shared_strings.append(''.join(texts))
                    log.info(f"Shared strings encontrados: {shared_strings[:10]}")

                # Leer sheet1.xml
                with z.open('xl/worksheets/sheet1.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
                    log.info(f"Namespace detectado: '{ns}'")

                    # Log de todas las filas y celdas encontradas
                    all_rows = root.findall(f'.//{ns}row')
                    log.info(f"Filas encontradas: {len(all_rows)}")
                    for i, row in enumerate(all_rows[:5]):
                        cells_info = []
                        for c in row.findall(f'{ns}c'):
                            r = c.get('r', '?')
                            t = c.get('t', 'n')
                            v = c.find(f'{ns}v')
                            cells_info.append(f"{r}(t={t},v={v.text if v is not None else 'None'})")
                        log.info(f"Fila {i}: {cells_info}")

                    rows_data = []
                    for row in root.findall(f'.//{ns}row'):
                        row_values = []
                        for c in row.findall(f'{ns}c'):
                            t = c.get('t', '')
                            v_el = c.find(f'{ns}v')
                            val = ''
                            if v_el is not None and v_el.text:
                                if t == 's':  # shared string
                                    val = shared_strings[int(v_el.text)]
                                else:
                                    val = v_el.text
                            row_values.append(val.strip())
                        if any(row_values):
                            rows_data.append(row_values)

            if not rows_data:
                return []

            headers = rows_data[0]
            products = [dict(zip(headers, row)) for row in rows_data[1:] if any(row)]
            log.info(f"XML directo parseado: {len(products)} productos.")
            return products

        except Exception as e2:
            log.error(f"Error leyendo XML directo: {e2}")
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


def get_all_places(page) -> list[dict]:
    """
    Extrae todas las sucursales disponibles en el selector del header.
    Espera a que Angular renderice el ng-repeat antes de extraer.
    """
    log.info("Extrayendo sucursales disponibles...")
    try:
        # Primero abrir el dropdown del header para que Angular renderice las opciones
        header = page.locator("div.fleft.ng-binding.ng-scope").first
        header.wait_for(state="visible", timeout=10000)
        header.click()
        page.wait_for_timeout(2000)

        # Esperar a que aparezcan los items del ng-repeat
        page.wait_for_selector("md-list-item[ng-repeat*='place in places']", timeout=8000)

        # Extraer placeId y nombre de cada sucursal via JS
        places = page.evaluate("""
            () => {
                const items = document.querySelectorAll('md-list-item[ng-repeat*="place in places"]');
                const results = [];
                for (const item of items) {
                    // Obtener el botón con ng-click="changePlace(...)"
                    const btn = item.querySelector('button[ng-click*="changePlace"]');
                    if (!btn) continue;
                    const ngClick = btn.getAttribute('ng-click') || '';
                    const match = ngClick.match(/changePlace\\((.+?)\\)/);
                    const placeId = match ? match[1].trim() : null;
                    // Obtener el nombre del elemento ng-binding
                    const nameEl = item.querySelector('.ng-binding');
                    const name = nameEl ? nameEl.textContent.trim() : `Sucursal ${results.length + 1}`;
                    if (placeId) results.push({ placeId, name });
                }
                return results;
            }
        """)

        # Cerrar el dropdown haciendo clic fuera
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        log.info(f"Sucursales encontradas: {[p['name'] for p in places]}")
        return places

    except Exception as e:
        log.error(f"Error extrayendo sucursales: {e}")
        return []


def switch_place(page, place_id: str, place_name: str) -> bool:
    """Cambia a la sucursal indicada abriendo el dropdown del header."""
    log.info(f"Cambiando a sucursal: {place_name}...")
    try:
        # Abrir dropdown
        header = page.locator("div.fleft.ng-binding.ng-scope").first
        header.wait_for(state="visible", timeout=8000)
        header.click()
        page.wait_for_timeout(1500)

        # Esperar opciones
        page.wait_for_selector("md-list-item[ng-repeat*='place in places']", timeout=8000)

        # Clic en la sucursal específica
        clicked = page.evaluate(f"""
            () => {{
                const items = document.querySelectorAll('md-list-item[ng-repeat*="place in places"]');
                for (const item of items) {{
                    const btn = item.querySelector('button[ng-click*="changePlace"]');
                    if (!btn) continue;
                    const ngClick = btn.getAttribute('ng-click') || '';
                    if (ngClick.includes('{place_id}')) {{
                        btn.click();
                        return btn.closest('md-list-item').querySelector('.ng-binding')?.textContent.trim() || 'ok';
                    }}
                }}
                return null;
            }}
        """)

        if clicked:
            log.info(f"Cambiado a '{clicked}' exitosamente.")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            return True
        else:
            log.error(f"No se encontró botón para placeId: {place_id}")
            return False
    except Exception as e:
        log.error(f"Error cambiando sucursal: {e}")
        return False


def scrape_all_places(username: str, password: str, headless: bool = True) -> list[dict]:
    """
    Función principal. Itera por todas las sucursales y retorna
    lista de dicts con {place_name, products}.
    """
    results = []

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

            # Obtener lista de sucursales
            places = get_all_places(page)
            if not places:
                log.warning("No se encontraron sucursales, intentando con sucursal actual...")
                places = [{"placeId": None, "name": "Principal"}]

            for place in places:
                place_name = place["name"]
                place_id   = place["placeId"]

                # Cambiar a la sucursal (si hay más de una)
                if place_id and len(places) > 1:
                    if not switch_place(page, place_id, place_name):
                        log.warning(f"Saltando sucursal '{place_name}'.")
                        continue

                # Navegar a stock y exportar
                if not navigate_to_stock(page):
                    log.warning(f"No se pudo navegar al stock de '{place_name}'.")
                    results.append({"place_name": place_name, "products": []})
                    continue

                products = export_and_parse(page)
                log.info(f"Sucursal '{place_name}': {len(products)} productos.")
                results.append({"place_name": place_name, "products": products})

        except Exception as e:
            log.error(f"Error durante el scraping: {e}")
            try:
                page.screenshot(path="/tmp/waitry_error.png")
            except Exception:
                pass
        finally:
            browser.close()

    return results


def scrape_waitry(username: str, password: str, headless: bool = True) -> list[dict]:
    """Mantiene compatibilidad — retorna productos de la primera sucursal."""
    results = scrape_all_places(username, password, headless)
    if results:
        return results[0]["products"]
    return []
