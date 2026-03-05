"""
Waitry Stock Scraper
Hace login en app.waitry.net, extrae datos de stock y genera un reporte PDF.
"""

import os
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def login(page, username: str, password: str) -> bool:
    """Inicia sesión en Waitry. Retorna True si fue exitoso."""
    log.info("Navegando al login de Waitry...")
    page.goto("https://app.waitry.net/", wait_until="networkidle")

    # Esperar campo de usuario
    page.wait_for_selector("input[type='email'], input[name='email'], input[name='username']", timeout=15000)

    # Completar credenciales
    email_input = page.locator("input[type='email'], input[name='email'], input[name='username']").first
    email_input.fill(username)

    password_input = page.locator("input[type='password']").first
    password_input.fill(password)

    # Click en botón de login
    page.locator("button[type='submit'], button:has-text('Ingresar'), button:has-text('Login'), button:has-text('Entrar')").first.click()

    try:
        # Esperar que la URL cambie (login exitoso)
        page.wait_for_url(lambda url: "login" not in url.lower(), timeout=15000)
        log.info("Login exitoso.")
        return True
    except PlaywrightTimeout:
        log.error("Falló el login. Verificar credenciales o estructura del formulario.")
        return False


def navigate_to_stock(page) -> bool:
    """Navega a la sección de stock/inventario."""
    log.info("Buscando sección de stock...")

    # Intentar múltiples selectores comunes en apps de restaurantes
    stock_selectors = [
        "a:has-text('Stock')",
        "a:has-text('Inventario')",
        "a:has-text('Productos')",
        "[href*='stock']",
        "[href*='inventory']",
        "[href*='inventario']",
        "nav a:has-text('Stock')",
    ]

    for selector in stock_selectors:
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=3000):
                element.click()
                page.wait_for_load_state("networkidle")
                log.info(f"Navegué a stock usando selector: {selector}")
                return True
        except Exception:
            continue

    log.warning("No se encontró enlace a stock automáticamente. Intentando URL directa...")
    for path in ["/stock", "/inventario", "/inventory", "/productos"]:
        try:
            base = page.url.split("/")[0] + "//" + page.url.split("/")[2]
            page.goto(base + path, wait_until="networkidle", timeout=8000)
            if "stock" in page.url or "invent" in page.url or "product" in page.url:
                return True
        except Exception:
            continue

    return False


def extract_stock_data(page) -> list[dict]:
    """
    Extrae tabla de stock de la página actual.
    Retorna lista de dicts con los datos encontrados.
    """
    log.info("Extrayendo datos de stock...")
    products = []

    try:
        # Esperar que haya contenido cargado
        page.wait_for_selector("table, [class*='table'], [class*='grid'], [class*='list']", timeout=10000)

        # Intentar extraer tabla HTML estándar
        rows = page.locator("table tbody tr").all()

        if rows:
            # Obtener headers
            headers = [th.inner_text().strip() for th in page.locator("table thead th").all()]
            log.info(f"Headers encontrados: {headers}")

            for row in rows:
                cells = [td.inner_text().strip() for td in row.locator("td").all()]
                if cells and any(c for c in cells):
                    if headers and len(cells) == len(headers):
                        products.append(dict(zip(headers, cells)))
                    else:
                        # Fallback: usar índices genéricos
                        products.append({f"col_{i}": v for i, v in enumerate(cells)})

        # Si no hay tabla HTML, intentar leer cards/grid
        if not products:
            cards = page.locator("[class*='product'], [class*='item'], [class*='card']").all()
            for card in cards:
                text = card.inner_text().strip()
                if text:
                    products.append({"descripcion": text})

    except PlaywrightTimeout:
        log.warning("Timeout esperando tabla de stock.")
    except Exception as e:
        log.error(f"Error extrayendo datos: {e}")

    log.info(f"Productos extraídos: {len(products)}")
    return products


def scrape_waitry(username: str, password: str, headless: bool = True) -> list[dict]:
    """Función principal de scraping. Retorna lista de productos con stock."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            if not login(page, username, password):
                return []

            if not navigate_to_stock(page):
                log.warning("No se pudo navegar a la sección de stock.")
                # Igual intentamos extraer lo que hay en pantalla
            
            data = extract_stock_data(page)
            return data

        except Exception as e:
            log.error(f"Error durante el scraping: {e}")
            # Guardar screenshot para debugging
            try:
                page.screenshot(path="/tmp/waitry_error.png")
                log.info("Screenshot guardado en /tmp/waitry_error.png")
            except Exception:
                pass
            return []

        finally:
            browser.close()
