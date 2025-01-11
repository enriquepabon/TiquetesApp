import os
import qrcode
import time
from datetime import datetime
import json
import traceback
import logging
from weasyprint import HTML
from flask import render_template
from config import app
from flask import render_template, current_app

logger = logging.getLogger(__name__)

def generate_qr(data, filename):
    try:
        logger.info("Iniciando generación de QR")
        
        # Generar nombre y ruta del archivo HTML
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_filename = f"guia_{data['codigo']}_{timestamp}.html"
        html_path = os.path.join(current_app.config['GUIAS_FOLDER'], html_filename)
        
        logger.info(f"Generando archivo HTML en: {html_path}")
        
        # Obtener los datos del tiquete
        html_content = render_template(
            'guia_template.html',
            codigo=data['codigo'],
            nombre=data.get('nombre', ''),
            fecha=data.get('fecha', ''),
            placa=data.get('placa', ''),
            cantidad_racimos=data.get('cantidad_racimos', ''),
            transportador=data.get('transportador', ''),
            image_filename=data.get('image_filename', '')
        )
        
        # Guardar el archivo HTML
        logger.info("Guardando archivo HTML...")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        logger.info(f"Archivo HTML guardado: {os.path.exists(html_path)}")
        
        # Generar URL para el QR
        base_url = "http://localhost:5002"
        url = f"{base_url}/guias/{html_filename}"
        
        logger.info(f"URL generada: {url}")
        
        # Generar QR
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        # Guardar QR
        qr_image = qr.make_image(fill_color="black", back_color="white")
        qr_image.save(filename)
        
        logger.info("QR generado exitosamente")
        return filename
        
    except Exception as e:
        logger.error(f"Error en generación: {str(e)}")
        logger.error(traceback.format_exc())
        raise


def generate_pdf(parsed_data, image_filename, fecha_procesamiento, hora_procesamiento, revalidation_data=None):
    """
    Genera un PDF con los datos del tiquete y el estado del proceso
    """
    try:
        now = datetime.now()
        fecha_emision = now.strftime("%Y-%m-%d")
        hora_emision = now.strftime("%H:%M:%S")
        
        # Preparar datos para el QR
        qr_data = {
            "codigo": revalidation_data.get('Código') if revalidation_data else parsed_data.get('codigo', ''),
            "nombre": revalidation_data.get('Nombre del Agricultor') if revalidation_data else parsed_data.get('nombre_agricultor', ''),
            "placa": parsed_data.get('placa', ''),
            "cantidad_racimos": parsed_data.get('cantidad_racimos', ''),
            "transportador": parsed_data.get('transportador', ''),
            "nota": revalidation_data.get('nota') if revalidation_data else parsed_data.get('nota', ''),
            "nombre_original": parsed_data.get('nombre_agricultor', ''),
            "codigo_original": parsed_data.get('codigo', ''),
            "revalidation_data": revalidation_data
        }
        
        logger.info(f"Preparando datos para PDF y QR: {qr_data}")
        
        # Generar QR
        qr_filename = f"qr_{qr_data['codigo']}_{int(time.time())}.png"
        qr_path = os.path.join(app.static_folder, qr_filename)
        generate_qr(qr_data, qr_path)
        
        # Renderizar PDF
        rendered = render_template(
            'pdf_template.html',
            parsed_data=parsed_data,
            revalidation_data=revalidation_data,
            image_filename=image_filename,
            fecha_procesamiento=fecha_procesamiento,
            hora_procesamiento=hora_procesamiento,
            fecha_emision=fecha_emision,
            hora_emision=hora_emision,
            qr_filename=qr_filename
        )
        
        # Generar nombre del PDF
        pdf_filename = f'tiquete_{qr_data["codigo"]}_{fecha_procesamiento}.pdf'
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        
        # Generar PDF
        HTML(
            string=rendered,
            base_url=app.static_folder
        ).write_pdf(pdf_path)
        
        logger.info(f"PDF generado exitosamente: {pdf_filename}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error generando PDF: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def upload_to_drive(service, file_path, folder_id=None):
    """
    Sube un archivo a Google Drive
    """
    try:
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id] if folder_id else []
        }
        
        media = None  # Aquí iría la configuración de MediaFileUpload
        
        logger.info(f"Subiendo archivo a Drive: {file_metadata['name']}")
        
        # Aquí iría la lógica de subida a Drive
        # Por ahora solo registramos el intento
        logger.info("Simulando subida a Drive (función no implementada)")
        
        return "drive_file_id_placeholder"
        
    except Exception as e:
        logger.error(f"Error subiendo a Drive: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def get_drive_service():
    """
    Obtiene el servicio de Google Drive
    """
    try:
        # Aquí iría la lógica de autenticación con Drive
        logger.info("Simulando conexión a Drive (función no implementada)")
        return None
        
    except Exception as e:
        logger.error(f"Error obteniendo servicio Drive: {str(e)}")
        logger.error(traceback.format_exc())
        raise

# Asegurar que existan los directorios necesarios
def ensure_directories():
    """
    Crea los directorios necesarios si no existen
    """
    try:
        directories = [
            app.config['UPLOAD_FOLDER'],
            app.config['PDF_FOLDER'],
            os.path.join(app.static_folder, 'qr')
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Directorio asegurado: {directory}")
            
    except Exception as e:
        logger.error(f"Error creando directorios: {str(e)}")
        logger.error(traceback.format_exc())
        raise

# Llamar a ensure_directories al importar el módulo
ensure_directories()