import os
import qrcode
import time
from datetime import datetime
import json
import traceback
import logging
from weasyprint import HTML
from flask import session, render_template, current_app

logger = logging.getLogger(__name__)

class Utils:
    def __init__(self, app):
        self.app = app
        self.ensure_directories()

    def ensure_directories(self, additional_directories=None):
        """
        Crea los directorios necesarios si no existen
        """
        try:
            # Directorios base
            directories = [
                os.path.join(self.app.static_folder, 'uploads'),
                os.path.join(self.app.static_folder, 'pdfs'),
                os.path.join(self.app.static_folder, 'guias'),
                os.path.join(self.app.static_folder, 'qr'),
                os.path.join(self.app.static_folder, 'images'),
                os.path.join(self.app.static_folder, 'excels')
            ]
            
            # Agregar directorios adicionales si existen
            if additional_directories:
                directories.extend(additional_directories)
                
            for directory in directories:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"Directorio asegurado: {directory}")
                
        except Exception as e:
            logger.error(f"Error creando directorios: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def generate_qr(self, data, filename):
        """
        Genera un archivo QR y su guía HTML asociada
        """
        try:
            logger.info("Iniciando generación de QR")
            
            # Obtener el código del proveedor y generar código de guía
            codigo_proveedor = data.get('codigo', '').strip()
            timestamp = datetime.now()
            fecha_hora = timestamp.strftime('%Y%m%d_%H%M%S')
            html_filename = f"guia_{codigo_proveedor}_{fecha_hora}.html"
            html_path = os.path.join(self.app.config['GUIAS_FOLDER'], html_filename)
            
            logger.info(f"Generando archivo HTML en: {html_path}")

            # Verificar existencia de imagen
            image_filename = data.get('image_filename', '')
            image_exists = False
            if image_filename:
                image_path = os.path.join(self.app.static_folder, 'uploads', image_filename)
                logger.info(f"Verificando imagen en: {image_path}")  # Agregar este log
                image_exists = os.path.exists(image_path)
                if not image_exists:
                    logger.warning(f"Imagen no encontrada en: {image_path}")
                    image_filename = None

                
            # Obtener fecha del tiquete y fecha actual
            fecha_tiquete = data.get('fecha', '')
            fecha_actual = timestamp.strftime('%d/%m/%Y')
            hora_actual = timestamp.strftime('%H:%M:%S')
            
            # Obtener los datos del tiquete
            html_content = render_template(
                'guia_template.html',
                codigo=codigo_proveedor,
                nombre=data.get('nombre', ''),
                fecha_tiquete=fecha_tiquete,
                fecha_registro=fecha_actual,
                fecha=data.get('fecha', ''),
                placa=data.get('placa', ''),
                cantidad_racimos=data.get('cantidad_racimos', ''),
                transportador=data.get('transportador', ''),
                estado_actual='pesaje',
                codigo_guia=f"{codigo_proveedor}_{fecha_hora}",
                fecha_formato=fecha_actual,
                hora_formato=hora_actual,  # Agregamos la coma aquí
                pdf_filename=session.get('pdf_filename', '')  # Ahora esta línea está correcta
            )
            
            # Guardar el archivo HTML
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                    
            logger.info(f"Archivo HTML guardado: {os.path.exists(html_path)}")
            
            # Generar URL para el QR
            base_url = "http://localhost:5002"
            url = f"{base_url}/guias/{html_filename}"
            
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
            
            logger.info(f"QR generado exitosamente en: {filename}")
            return filename
                
        except Exception as e:
            logger.error(f"Error en generación QR: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def generate_pdf(self, parsed_data, image_filename, fecha_procesamiento, hora_procesamiento, revalidation_data=None):
        """
        Genera un PDF con los datos del tiquete
        """
        try:
            logger.info("Iniciando generación de PDF")
            logger.info(f"Datos de revalidación: {revalidation_data}")
            
            # Verificar y crear logo si no existe
            logo_path = os.path.join(self.app.static_folder, 'images', 'logo-oleoflores.png')
            if not os.path.exists(logo_path):
                logger.warning("Logo no encontrado. Se omitirá en el PDF")
            
            now = datetime.now()
            
            # Formatear fecha del tiquete
            fecha_tiquete = self.format_date(parsed_data)
            
            # Preparar datos para el PDF
            context = {
                'parsed_data': parsed_data,
                'revalidation_data': revalidation_data,
                'image_filename': image_filename,
                'fecha_registro': fecha_tiquete,
                'fecha_procesamiento': fecha_procesamiento,
                'hora_procesamiento': hora_procesamiento,
                'fecha_emision': now.strftime("%d/%m/%Y"),
                'hora_emision': now.strftime("%H:%M:%S"),
                'logo_exists': os.path.exists(logo_path),
                'qr_filename': session.get('qr_filename', '')
            }

            # Generar PDF
            rendered = render_template('pdf_template.html', **context)
            
            # Obtener código del tiquete
            codigo = self.get_codigo_from_data(parsed_data)
            
            # Generar nombre del archivo
            pdf_filename = f'tiquete_{codigo}_{fecha_tiquete.replace("/", "-")}.pdf'
            pdf_path = os.path.join(self.app.config['PDF_FOLDER'], pdf_filename)

            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            
            HTML(
                string=rendered,
                base_url=self.app.static_folder
            ).write_pdf(pdf_path)
            
            logger.info(f"PDF generado exitosamente: {pdf_filename}")
            return pdf_filename
            
        except Exception as e:
            logger.error(f"Error en generate_pdf: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def format_date(self, parsed_data):
        """
        Formatea la fecha del tiquete en un formato consistente
        """
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_str = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                try:
                    for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            return datetime.strptime(fecha_str, fmt).strftime("%d/%m/%Y")
                        except ValueError:
                            continue
                except Exception as e:
                    logger.error(f"Error parseando fecha: {str(e)}")
                    return fecha_str
        return datetime.now().strftime("%d/%m/%Y")

    def get_codigo_from_data(self, parsed_data):
        """
        Obtiene el código del tiquete de los datos parseados
        """
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Código':
                return row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
        return 'desconocido'

    def generar_codigo_guia(self, codigo_proveedor):
        """
        Genera un código único para la guía
        """
        now = datetime.now()
        fecha_formateada = now.strftime('%d%m%Y')
        hora_formateada = now.strftime('%H%M')
        return f"{codigo_proveedor}_{fecha_formateada}_{hora_formateada}"

    def registrar_fecha_porteria(self):
        """
        Registra la fecha actual de entrada en portería
        """
        return datetime.now().strftime('%d/%m/%Y %H:%M')

    def get_ticket_date(self, parsed_data):
        """
        Obtiene la fecha del tiquete de los datos parseados
        """
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_str = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                try:
                    for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            fecha_obj = datetime.strptime(fecha_str, fmt)
                            return fecha_obj.strftime("%d/%m/%Y")
                        except ValueError:
                            continue
                except Exception as e:
                    logger.error(f"Error parseando fecha: {str(e)}")
                    return fecha_str
        return datetime.now().strftime("%d/%m/%Y")

    def prepare_revalidation_data(self, parsed_data, data):
        """
        Prepara los datos de revalidación
        """
        revalidation_data = {}
        for row in parsed_data.get('table_data', []):
            campo = row['campo']
            valor = row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
            revalidation_data[campo] = valor

        if data:
            if data.get('Nombre'):
                revalidation_data['Nombre del Agricultor'] = data['Nombre']
            if data.get('Codigo'):
                revalidation_data['Código'] = data['Codigo']
            if data.get('Nota'):
                revalidation_data['nota'] = data['Nota']

        return revalidation_data


# Para mantener compatibilidad con código existente que no use la clase
utils = None

def init_utils(app):
    global utils
    utils = Utils(app)
    return utils