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

logger = logging.getLogger(__name__)

def generate_qr(data, filename):
    """
    Genera un código QR con la información completa del proceso de registro.
    Incluye el estado actual y espacios para futuros estados del proceso.
    """
    try:
        logger.info("Iniciando generación de QR")
        logger.info(f"Datos recibidos: {data}")
        
        # Obtener fecha y hora actual
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Estructurar los datos del proceso completo
        process_data = {
            "id_tiquete": data.get("codigo", ""),
            "fecha_registro": current_time,
            "datos_registro": {
                "agricultor": data.get("nombre", ""),
                "codigo": data.get("codigo", ""),
                "placa": data.get("placa", ""),
                "cantidad_racimos": data.get("cantidad_racimos", ""),
                "transportador": data.get("transportador", ""),
                "nota_validacion": data.get("nota", "")
            },
            "estados_proceso": {
                "registro": {
                    "estado": "completado",
                    "fecha": current_time,
                    "usuario": "sistema"
                },
                "peso_bruto": {
                    "estado": "pendiente",
                    "fecha": None,
                    "peso": None,
                    "usuario": None
                },
                "clasificacion": {
                    "estado": "pendiente",
                    "fecha": None,
                    "calidad": None,
                    "usuario": None
                },
                "cierre": {
                    "estado": "pendiente",
                    "fecha": None,
                    "peso_neto": None,
                    "usuario": None
                }
            },
            "modificaciones": [],
            "url_seguimiento": f"/seguimiento-tiquete/{data.get('codigo', '')}"
        }
        
        # Si hubo revalidación, agregar la información
        if data.get("revalidation_data"):
            process_data["modificaciones"].append({
                "fecha": current_time,
                "tipo": "revalidacion",
                "cambios": {
                    "nombre_anterior": data.get("nombre_original", ""),
                    "nombre_nuevo": data.get("nombre", ""),
                    "codigo_anterior": data.get("codigo_original", ""),
                    "codigo_nuevo": data.get("codigo", "")
                }
            })

        logger.info(f"Datos estructurados para QR: {process_data}")
        
        # Generar el QR
        qr = qrcode.QRCode(
            version=None,  # Automático
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Alta corrección de errores
            box_size=10,
            border=4,
        )
        
        # Convertir a JSON y agregar al QR
        qr_data = json.dumps(process_data, ensure_ascii=False)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Crear la imagen
        qr_image = qr.make_image(fill_color="black", back_color="white")
        qr_image.save(filename)
        
        logger.info(f"QR generado exitosamente: {filename}")
        return filename
        
    except Exception as e:
        logger.error(f"Error generando QR: {str(e)}")
        logger.error(traceback.format_exc())
        raise Exception(f"Error en generación de QR: {str(e)}")

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