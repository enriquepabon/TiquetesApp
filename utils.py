from flask import render_template
from weasyprint import HTML
from datetime import datetime
import qrcode
import os
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import app

logger = logging.getLogger(__name__)
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def generate_qr(data, output_path):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white")
    qr_image.save(output_path)
    return output_path

def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(service, file_path, folder_id=None):
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id] if folder_id else []
    }
    
    media = MediaFileUpload(file_path, resumable=True)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    return file.get('id')

def generate_pdf(parsed_data, image_filename, fecha_procesamiento, hora_procesamiento):
    now = datetime.now()
    fecha_emision = now.strftime("%Y-%m-%d")
    hora_emision = now.strftime("%H:%M:%S")
    
    # Generar QR
    qr_data = {
        "id": parsed_data.get("id", ""),
        "nombre": parsed_data.get("nombre_agricultor", ""),
        "codigo": parsed_data.get("codigo", ""),
        "fecha": fecha_procesamiento
    }
    
    qr_filename = f'qr_{parsed_data.get("codigo", "")}_{int(datetime.now().timestamp())}.png'
    qr_path = os.path.join(app.static_folder, qr_filename)
    generate_qr(str(qr_data), qr_path)
    
    # Generar PDF
    rendered = render_template(
        'pdf_template.html',
        parsed_data=parsed_data,
        image_filename=image_filename,
        fecha_procesamiento=fecha_procesamiento,
        hora_procesamiento=hora_procesamiento,
        fecha_emision=fecha_emision,
        hora_emision=hora_emision,
        qr_filename=qr_filename
    )
    
    pdf_filename = f'tiquete_{parsed_data.get("codigo", "")}_{fecha_procesamiento}.pdf'
    pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
    
    HTML(string=rendered, base_url=app.static_folder).write_pdf(pdf_path)
    
    # Subir a Drive
    try:
        service = get_drive_service()
        file_id = upload_to_drive(service, pdf_path, 'FOLDER_ID')  # Reemplazar con tu ID
        return pdf_filename, file_id, qr_filename
    except Exception as e:
        logger.error(f"Error subiendo a Drive: {str(e)}")
        return pdf_filename, None, qr_filename