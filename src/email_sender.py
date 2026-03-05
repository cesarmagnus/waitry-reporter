"""
Envío del reporte PDF por email.
Soporta SMTP genérico (Gmail, Outlook, SendGrid, etc.)
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


def send_report(
    pdf_path: str,
    recipients: list[str],
    place_name: str = "Cafetería",
    report_date: datetime | None = None
) -> bool:
    """
    Envía el reporte PDF por email.
    
    Variables de entorno necesarias:
        SMTP_HOST     - Servidor SMTP (ej: smtp.gmail.com)
        SMTP_PORT     - Puerto (ej: 587)
        SMTP_USER     - Email del remitente
        SMTP_PASSWORD - Contraseña o App Password
        EMAIL_FROM    - Nombre visible del remitente (opcional)
    
    Returns:
        True si se envió correctamente, False en caso de error.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        log.error("Faltan variables SMTP_USER y/o SMTP_PASSWORD.")
        return False

    if report_date is None:
        report_date = datetime.now()

    date_str   = report_date.strftime("%d/%m/%Y")
    subject    = f"📦 Reporte de Stock — {place_name} — {date_str}"
    pdf_name   = Path(pdf_path).name

    # ── Construir email ────────────────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["From"]    = f"{place_name} <{email_from}>"
    msg["To"]      = ", ".join(recipients)
    msg["Subject"] = subject

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1A1A2E; background: #F4F6FB; margin:0; padding:20px;">
      <div style="max-width:560px; margin:auto; background:white; border-radius:10px;
                  box-shadow:0 2px 8px rgba(0,0,0,0.08); overflow:hidden;">
        
        <div style="background:#1A1A2E; padding:24px 28px;">
          <h1 style="color:white; margin:0; font-size:20px;">📦 Reporte de Stock</h1>
          <p style="color:#AAB4C8; margin:4px 0 0;">{place_name} &nbsp;·&nbsp; {date_str}</p>
        </div>

        <div style="padding:24px 28px;">
          <p>Hola,</p>
          <p>Adjunto encontrás el reporte diario de inventario de <strong>{place_name}</strong>
             correspondiente al <strong>{date_str}</strong>.</p>
          <p>El reporte incluye:</p>
          <ul>
            <li>Resumen ejecutivo con totales</li>
            <li>Alertas de productos sin stock o con stock bajo</li>
            <li>Detalle completo de todos los productos</li>
          </ul>
          <p style="color:#6C757D; font-size:13px;">
            Este reporte fue generado automáticamente desde Waitry.
          </p>
        </div>

        <div style="background:#F4F6FB; padding:14px 28px; font-size:12px; color:#6C757D;">
          Generado automáticamente — {report_date.strftime("%d/%m/%Y %H:%M")}
        </div>
      </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_body, "html"))

    # Adjuntar PDF
    with open(pdf_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_name)
        msg.attach(attachment)

    # ── Enviar ─────────────────────────────────────────────────────────────
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, recipients, msg.as_string())

        log.info(f"Email enviado a: {', '.join(recipients)}")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error("Error de autenticación SMTP. Verificar usuario/contraseña.")
    except smtplib.SMTPException as e:
        log.error(f"Error SMTP: {e}")
    except Exception as e:
        log.error(f"Error inesperado enviando email: {e}")

    return False
