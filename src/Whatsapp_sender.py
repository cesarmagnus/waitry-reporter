"""
Envío del reporte PDF por WhatsApp usando la API de Meta (Cloud API).
Sube cada PDF como documento y lo envía a los destinatarios configurados.
"""

import os
import logging
import requests
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v19.0"


def _upload_media(pdf_path: str, token: str, phone_number_id: str) -> str | None:
    """Sube un PDF a los servidores de Meta y retorna el media_id."""
    url = f"{WHATSAPP_API_URL}/{phone_number_id}/media"
    try:
        with open(pdf_path, "rb") as f:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (Path(pdf_path).name, f, "application/pdf")},
                data={"messaging_product": "whatsapp"},
                timeout=30,
            )
        if response.status_code == 200:
            media_id = response.json().get("id")
            log.info(f"PDF subido exitosamente. media_id: {media_id}")
            return media_id
        else:
            log.error(f"Error subiendo PDF: {response.status_code} — {response.text}")
            return None
    except Exception as e:
        log.error(f"Excepción subiendo PDF: {e}")
        return None


def _send_document(media_id: str, filename: str, caption: str,
                   recipient: str, token: str, phone_number_id: str) -> bool:
    """Envía un documento ya subido (por media_id) a un destinatario."""
    url = f"{WHATSAPP_API_URL}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
            "caption": caption,
        },
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if response.status_code == 200:
            log.info(f"Documento enviado a {recipient} exitosamente.")
            return True
        else:
            log.error(f"Error enviando documento a {recipient}: {response.status_code} — {response.text}")
            return False
    except Exception as e:
        log.error(f"Excepción enviando documento: {e}")
        return False


def _send_text(message: str, recipient: str, token: str, phone_number_id: str) -> bool:
    """Envía un mensaje de texto simple."""
    url = f"{WHATSAPP_API_URL}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": message},
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        return response.status_code == 200
    except Exception as e:
        log.error(f"Error enviando texto: {e}")
        return False


def send_whatsapp_report(
    pdf_paths: list[tuple[str, str]],
    place_name: str = "Cafetería",
    report_date: datetime | None = None,
) -> bool:
    """
    Envía los PDFs de stock por WhatsApp a los destinatarios configurados.

    Variables de entorno necesarias:
        WHATSAPP_TOKEN          - Token de acceso de Meta
        WHATSAPP_PHONE_ID       - Phone Number ID de Meta
        WHATSAPP_RECIPIENTS     - Números separados por coma (ej: 56912345678,56987654321)
    """
    token          = os.getenv("WHATSAPP_TOKEN")
    phone_id       = os.getenv("WHATSAPP_PHONE_ID")
    recipients_raw = os.getenv("WHATSAPP_RECIPIENTS", "")
    recipients     = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    if not token or not phone_id:
        log.error("Faltan variables WHATSAPP_TOKEN y/o WHATSAPP_PHONE_ID.")
        return False

    if not recipients:
        log.error("Falta variable WHATSAPP_RECIPIENTS.")
        return False

    if report_date is None:
        report_date = datetime.now()

    date_str = report_date.strftime("%d/%m/%Y %H:%M")
    success  = True

    intro = (
        f"📦 *Reporte de Stock — Pastelería*\n"
        f"📍 {place_name}\n"
        f"🗓 {date_str}\n\n"
        f"Adjunto encontrás el stock de cada sucursal:"
    )

    for recipient in recipients:
        _send_text(intro, recipient, token, phone_id)

        for sucursal_name, pdf_path in pdf_paths:
            media_id = _upload_media(pdf_path, token, phone_id)
            if not media_id:
                log.error(f"No se pudo subir PDF de '{sucursal_name}'.")
                success = False
                continue

            safe_name = sucursal_name.replace(" ", "_")
            filename  = f"stock_{safe_name}_{report_date.strftime('%Y%m%d')}.pdf"
            caption   = f"📍 {sucursal_name}"
            ok = _send_document(media_id, filename, caption, recipient, token, phone_id)
            if not ok:
                success = False

    return success
