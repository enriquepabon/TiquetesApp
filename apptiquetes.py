from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, current_app
import os
import requests
from werkzeug.utils import secure_filename
from datetime import datetime
from weasyprint import HTML
import tempfile
import logging
import traceback
import mimetypes
import time
import json
import qrcode
from io import BytesIO
from PIL import Image
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from parser import parse_markdown_response
from config import app
from utils import Utils
import random
import string
from datetime import datetime, timedelta
from knowledge_updater import knowledge_bp


# Configuración de Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Inicializar Utils
utils = Utils(app)

app.register_blueprint(knowledge_bp)

# En apptiquetes.py, al inicio después de las importaciones
# Configuración de carpetas usando Utils
REQUIRED_FOLDERS = [
    os.path.join(app.static_folder, 'images'),
    os.path.join(app.static_folder, 'uploads'),
    os.path.join(app.static_folder, 'pdfs'),
    os.path.join(app.static_folder, 'guias'),
    os.path.join(app.static_folder, 'qr')
]


utils.ensure_directories(REQUIRED_FOLDERS)



for folder in REQUIRED_FOLDERS:
    os.makedirs(folder, exist_ok=True)


# Configuración de carpetas
app.config.update(
    GUIAS_FOLDER=os.path.join(app.static_folder, 'guias'),
    UPLOAD_FOLDER=os.path.join(app.static_folder, 'uploads'),
    PDF_FOLDER=os.path.join(app.static_folder, 'pdfs'),
    EXCEL_FOLDER=os.path.join(app.static_folder, 'excels'),
    SECRET_KEY='tu_clave_secreta_aquí'
)

# Crear directorios necesarios
for folder in ['GUIAS_FOLDER', 'UPLOAD_FOLDER', 'PDF_FOLDER', 'EXCEL_FOLDER']:
    os.makedirs(app.config[folder], exist_ok=True)

@app.route('/guias/<filename>')
def serve_guia(filename):
    """
    Sirve los archivos HTML de las guías de proceso
    """
    try:
        logger.info(f"Intentando servir guía: {filename}")
        return send_from_directory(app.config['GUIAS_FOLDER'], filename)
    except Exception as e:
        logger.error(f"Error sirviendo guía: {str(e)}")
        return render_template('error.html', message="Guía no encontrada"), 404

# URLs de los Webhooks en Make.com
PROCESS_WEBHOOK_URL = "https://hook.us2.make.com/asrfb3kv3cw4o4nd43wylyasfx5yq55f"
REGISTER_WEBHOOK_URL = "https://hook.us2.make.com/f63o7rmsuixytjfqxq3gjljnscqhiedl"
REVALIDATION_WEBHOOK_URL = "https://hook.us2.make.com/bok045bvtwpj89ig58nhrmx1x09yh56u"
ADMIN_NOTIFICATION_WEBHOOK_URL = "https://hook.us2.make.com/wpeskbay7k21c3jnthu86lyo081r76fe"
PESAJE_WEBHOOK_URL = "https://hook.us2.make.com/srw5ti54ulwuxtvocrj2lypa5pmq3im4"
AUTORIZACION_WEBHOOK_URL = "https://hook.us2.make.com/py29fwgfrehp9il45832acotytu8xr5s"
REGISTRO_PESO_WEBHOOK_URL = "https://hook.us2.make.com/agxyjbyswl2cg1bor1wdrlfcgrll0y15"

codigos_autorizacion = {}


# Extensiones permitidas para subir
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    session.clear()
    
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            try:
                # Generar nombre seguro para el archivo
                filename = secure_filename(file.filename)
                # Asegurar que el directorio de uploads existe
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                # Guardar el archivo
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(image_path)
                
                # Verificar que el archivo se guardó correctamente
                if os.path.exists(image_path):
                    session['image_filename'] = filename
                    logger.info(f"Imagen guardada exitosamente: {image_path}")
                    return redirect(url_for('processing'))
                else:
                    logger.error(f"Error: El archivo no se guardó correctamente en {image_path}")
                    return render_template('error.html', message="Error al guardar el archivo.")
                    
            except Exception as e:
                logger.error(f"Error guardando archivo: {str(e)}")
                return render_template('error.html', message="Error procesando el archivo.")
        else:
            return render_template('error.html', message="Tipo de archivo no permitido o no se ha seleccionado ningún archivo.")
    return render_template('index.html')

@app.route('/processing')
def processing():
    image_filename = session.get('image_filename')
    if not image_filename:
        return render_template('error.html', message="No se encontró una imagen para procesar.")
    return render_template('processing.html')

@app.route('/process_image', methods=['POST'])
def process_image():
    """
    Ruta que maneja el envío de la imagen al webhook y retorna la respuesta parseada.
    """
    image_filename = session.get('image_filename')
    if not image_filename:
        return jsonify({"result": "error", "message": "No se encontró una imagen para procesar."}), 400
    
    try:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        
        if not os.path.exists(image_path):
            logger.error(f"Archivo no encontrado: {image_path}")
            return jsonify({"result": "error", "message": "Archivo no encontrado."}), 404
        
        # Verificaciones de archivo...
        with open(image_path, 'rb') as f:
            files = {'file': (image_filename, f, 'multipart/form-data')}
            response = requests.post(PROCESS_WEBHOOK_URL, files=files)
            
        logger.info(f"Respuesta del Webhook: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            return jsonify({"result": "error", "message": f"Error del webhook: {response.text}"}), 500
            
        # Obtener y verificar la respuesta del texto
        response_text = response.text.strip()
        if not response_text:
            return jsonify({"result": "error", "message": "Respuesta vacía del webhook."}), 500
            
        # Procesar la respuesta
        parsed_data = parse_markdown_response(response_text)
        if not parsed_data:
            logger.error("No se pudieron parsear los datos de la respuesta.")
            return jsonify({"result": "error", "message": "No se pudieron parsear los datos."}), 500
        
        # Guardar en sesión
        session['parsed_data'] = parsed_data
        return jsonify({"result": "ok"})
        
    except Exception as e:
        logger.error(f"Error al procesar la imagen: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "result": "error", 
            "message": f"Error al procesar la imagen: {str(e)}"
        }), 500
    
@app.route('/review', methods=['GET'])
def review():
    """
    Muestra la página de revisión con la tabla de tres columnas.
    """
    parsed_data = session.get('parsed_data', {})
    image_filename = session.get('image_filename', '')
    
    if not parsed_data or not image_filename:
        return render_template('error.html', message="No hay datos para revisar.")
    
    if 'table_data' not in parsed_data:
        logger.error("Formato de datos incorrecto")
        return render_template('error.html', message="Error en el formato de los datos.")
    
    timestamp = datetime.now().timestamp()
    
    return render_template(
        'review.html',
        image_filename=image_filename,
        parsed_data=parsed_data,
        timestamp=timestamp
    )

# En apptiquetes.py, ruta update_data
@app.route('/update_data', methods=['POST'])
def update_data():
    try:
        logger.info("Iniciando proceso de update_data")
        updated_data = request.get_json()
        logger.info(f"Datos recibidos en update_data: {updated_data}")
        
        # Actualizar los datos en la sesión
        parsed_data = session.get('parsed_data', {})
        table_data = updated_data.get('table_data', [])
        
        # Actualizar todos los campos en parsed_data
        for row in table_data:
            campo = row.get('campo')
            valor_modificado = row.get('sugerido', '').strip()
            
            # Buscar y actualizar en parsed_data
            for original_row in parsed_data.get('table_data', []):
                if original_row['campo'] == campo:
                    original_row['sugerido'] = valor_modificado
        
        # Guardar parsed_data actualizado en sesión
        session['parsed_data'] = parsed_data
        logger.info(f"Datos actualizados en sesión: {parsed_data}")

        # Si hay campos críticos modificados (nombre o código), revalidar
        modifications = []
        for row in table_data:
            if row.get('campo') in ['Nombre del Agricultor', 'Código']:
                valor_anterior = str(row.get('original', '')).strip()
                valor_modificado = str(row.get('sugerido', '')).strip()
                if valor_modificado != valor_anterior:
                    modifications.append({
                        "campo": row['campo'],
                        "valor_anterior": valor_anterior,
                        "valor_modificado": valor_modificado
                    })

        if modifications:
            try:
                response = requests.post(
                    REVALIDATION_WEBHOOK_URL,
                    json={"json": {"modificaciones": modifications}},
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                
                logger.info(f"Respuesta del webhook - Status: {response.status_code}")
                logger.info(f"Respuesta del webhook - Texto: {response.text}")
                
                if response.status_code == 200:
                    try:
                        webhook_data = response.json()
                        return jsonify({
                            "status": "success",
                            "data": {
                                "Result": webhook_data.get('Body', {}).get('Resultado', ''),
                                "Codigo": webhook_data.get('Body', {}).get('Codigo', ''),
                                "Nombre": webhook_data.get('Body', {}).get('Nombre', ''),
                                "Nota": webhook_data.get('Body', {}).get('Nota', ''),
                                "modificaciones": modifications,
                                "webhook_status": response.status_code
                            }
                        })
                    except ValueError:
                        webhook_text = response.text
                        if isinstance(webhook_text, str):
                            webhook_data = {
                                'Body': {
                                    'Resultado': next((l.replace('Resultado:', '').strip() for l in webhook_text.split('\n') if 'Resultado:' in l), ''),
                                    'Codigo': next((l.replace('Codigo:', '').strip().strip('"') for l in webhook_text.split('\n') if 'Codigo:' in l), ''),
                                    'Nombre': next((l.replace('Nombre:', '').strip().strip('"') for l in webhook_text.split('\n') if 'Nombre:' in l), ''),
                                    'Nota': next((l.replace('Nota:', '').strip() for l in webhook_text.split('\n') if 'Nota:' in l), '')
                                }
                            }
                            return jsonify({
                                "status": "success",
                                "data": {
                                    "Result": webhook_data['Body']['Resultado'],
                                    "Codigo": webhook_data['Body']['Codigo'],
                                    "Nombre": webhook_data['Body']['Nombre'],
                                    "Nota": webhook_data['Body']['Nota'],
                                    "modificaciones": modifications,
                                    "webhook_status": response.status_code
                                }
                            })
                else:
                    raise Exception(f"Error en webhook: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error en petición al webhook: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": f"Error de conexión: {str(e)}"
                }), 500
                
        return jsonify({
            "status": "success",
            "message": "No se requieren cambios para revalidación"
        })
            
    except Exception as e:
        logger.error(f"Error general: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/processing', methods=['GET'])
def processing_screen():
    """
    Pantalla de carga mientras se procesa la revalidación.
    """
    return render_template('processing.html')


# >>> NUEVO: Función para generar QR y devolver su nombre o ruta
def generate_qr_image(codigo, nombre, fruta):
    """
    Genera un archivo PNG de código QR que contenga info clave (código, agricultor, fruta).
    Retorna el nombre de archivo PNG.
    """
    content = f"Código: {codigo}\nAgricultor: {nombre}\nFruta: {fruta}"
    qr_img = qrcode.make(content)
    
    # Guardarlo en static con un nombre único
    qr_filename = f"qr_{codigo}_{int(time.time())}.png"
    qr_path = os.path.join(app.static_folder, qr_filename)
    qr_img.save(qr_path)
    
    # Retornar sólo el nombre, para usarlo en la plantilla
    return qr_filename


def generate_pdf(parsed_data, image_filename, fecha_procesamiento, hora_procesamiento, revalidation_data=None):
    """
    Genera un PDF a partir de los datos del tiquete.
    """
    try:
        logger.info("Iniciando generación de PDF")
        logger.info(f"Datos de revalidación: {revalidation_data}")
        
        # Obtener fecha original del tiquete
        fecha_registro = None
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_registro = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                break
        
        if not fecha_registro:
            fecha_registro = datetime.now().strftime("%d-%m-%Y")
        
        # Preparar datos para el QR
        qr_data = {
            "codigo": revalidation_data.get('Código') if revalidation_data else parsed_data.get('codigo', ''),
            "nombre": revalidation_data.get('Nombre del Agricultor') if revalidation_data else parsed_data.get('nombre_agricultor', ''),
            "fecha": fecha_registro,
            "placa": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Placa'), ''),
            "transportador": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Transportador'), ''),
            "cantidad_racimos": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Cantidad de Racimos'), '')
        }
        
        qr_filename = f"qr_{qr_data['codigo']}_{int(time.time())}.png"
        qr_path = os.path.join(app.static_folder, qr_filename)
        utils.generate_qr(qr_data, qr_path)
        
        # Renderizar plantilla
        rendered = render_template(
            'pdf_template.html',
            parsed_data=parsed_data,
            revalidation_data=revalidation_data,
            image_filename=image_filename,
            fecha_registro=fecha_registro,
            fecha_procesamiento=fecha_registro,  # Usar la fecha del tiquete
            hora_procesamiento=hora_procesamiento,
            fecha_emision=datetime.now().strftime("%d-%m-%Y"),
            hora_emision=datetime.now().strftime("%H:%M:%S"),
            qr_filename=qr_filename
        )
        
        # Generar PDF
        pdf_filename = f'tiquete_{qr_data["codigo"]}_{fecha_registro}.pdf'
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        HTML(
            string=rendered,
            base_url=app.static_folder
        ).write_pdf(pdf_path)
        
        logger.info(f"PDF generado exitosamente: {pdf_filename}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error en generate_pdf: {str(e)}")
        logger.error(traceback.format_exc())
        raise Exception(f"Error generando PDF: {str(e)}")

@app.route('/register', methods=['POST'])
def register():
    try:
        logger.info("Iniciando proceso de registro")
        
        parsed_data = session.get('parsed_data', {})
        image_filename = session.get('image_filename', '')
        
        if not parsed_data or not image_filename:
            return jsonify({
                "status": "error",
                "message": "No hay datos para registrar."
            }), 400

        try:
            data = request.get_json() if request.is_json else {}
            
            fecha_tiquete = utils.get_ticket_date(parsed_data)
            hora_procesamiento = datetime.now().strftime("%H:%M:%S")
            
            revalidation_data = utils.prepare_revalidation_data(parsed_data, data)
            
            # Enviar datos al webhook de registro
            try:
                response = requests.post(
                    REGISTER_WEBHOOK_URL,
                    json={
                        "parsed_data": parsed_data,
                        "revalidation_data": revalidation_data,
                        "fecha": fecha_tiquete,
                        "hora": hora_procesamiento
                    },
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code != 200:
                    logger.error(f"Error en webhook de registro: {response.text}")
                    raise Exception("Error al registrar en el sistema central")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error llamando webhook de registro: {str(e)}")
                raise Exception("Error de conexión con el sistema central")
            
            # Generar QR
            codigo = revalidation_data.get('Código', '')
            timestamp = int(time.time())
            qr_filename = f"qr_{codigo}_{timestamp}.png"
            qr_path = os.path.join(app.static_folder, qr_filename)
            
            # Preparar datos para el QR
            qr_data = {
                "codigo": codigo,
                "nombre": revalidation_data.get('Nombre del Agricultor', ''),
                "fecha": fecha_tiquete,
                "placa": revalidation_data.get('Placa', ''),
                "transportador": revalidation_data.get('Transportador', ''),
                "cantidad_racimos": revalidation_data.get('Cantidad de Racimos', '')
            }
            
            utils.generate_qr(qr_data, qr_path)
            session['qr_filename'] = qr_filename
            
            # Generar PDF
            pdf_filename = utils.generate_pdf(
                parsed_data=parsed_data,
                image_filename=image_filename,
                fecha_procesamiento=fecha_tiquete,
                hora_procesamiento=hora_procesamiento,
                revalidation_data=revalidation_data
            )
            
            session['pdf_filename'] = pdf_filename
            session['revalidation_data'] = revalidation_data
            session['estado_actual'] = 'pesaje'
            
            return jsonify({
                "status": "success",
                "message": "Registro completado exitosamente",
                "pdf_filename": pdf_filename,
                "qr_filename": qr_filename
            })
            
        except Exception as e:
            logger.error(f"Error procesando registro: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"Error procesando registro: {str(e)}"
            }), 500
            
    except Exception as e:
        logger.error(f"Error general en registro: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error al registrar: {str(e)}"
        }), 500


    
@app.route('/review_pdf')
def review_pdf():
    """
    Muestra una página con el enlace del PDF generado y el código QR.
    """
    pdf_filename = session.get('pdf_filename')
    qr_filename = session.get('qr_filename')  # Asegúrate de que este valor se está guardando en la sesión
    
    if not pdf_filename or not qr_filename:
        return render_template('error.html', message="No se encontró el PDF o QR generado.")
    
    return render_template('review_pdf.html', 
                         pdf_filename=pdf_filename,
                         qr_filename=qr_filename)

@app.route('/test_webhook', methods=['GET'])
def test_webhook():
    """
    Ruta de prueba para verificar la conectividad con el webhook.
    """
    try:
        response = requests.get(PROCESS_WEBHOOK_URL)
        return jsonify({
            "status": "webhook accessible" if response.status_code == 200 else "webhook error",
            "status_code": response.status_code,
            "response": response.text
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', message="Página no encontrada."), 404

@app.route('/test_revalidation', methods=['GET'])
def test_revalidation():
    test_payload = {
        "modificaciones": [
            {
                "campo": "Nombre del Agricultor",
                "valor_anterior": "Test Nombre",
                "valor_modificado": "Test Modificado"
            }
        ]
    }
    
    try:
        response = requests.post(
            REVALIDATION_WEBHOOK_URL,
            json=test_payload,
            headers={'Content-Type': 'application/json'}
        )
        
        return jsonify({
            "status": response.status_code,
            "response": response.text,
            "sent_payload": test_payload
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/revalidation_results')
def revalidation_results():
    """
    Renderiza la página de resultados de revalidación
    """
    return render_template('revalidation_results.html')

@app.route('/pesaje-inicial/<codigo>', methods=['GET', 'POST'])
def pesaje_inicial(codigo):
    """Manejo de pesaje inicial (directo o virtual)"""
    pass

@app.route('/clasificacion/<codigo>', methods=['GET', 'POST'])
def clasificacion(codigo):
    """Manejo de clasificación de fruta (automático o manual)"""
    pass

@app.route('/pesaje-tara/<codigo>', methods=['GET', 'POST'])
def pesaje_tara(codigo):
    """Manejo de pesaje tara y generación de documentos"""
    pass

@app.route('/salida/<codigo>', methods=['GET', 'POST'])
def salida(codigo):
    """Manejo de proceso de salida y cierre de guía"""
    pass

@app.route('/seguimiento-guia/<codigo>')
def seguimiento_guia(codigo):
    """Vista de seguimiento completo del proceso"""
    pass

@app.route('/actualizar-estado/<codigo>', methods=['POST'])
def actualizar_estado(codigo):
    """API para actualizar el estado de cualquier etapa del proceso"""
    pass

@app.route('/pesaje/<codigo>', methods=['GET', 'POST'])
def pesaje(codigo):
    """
    Maneja la vista de pesaje y el procesamiento del mismo
    """
    try:
        # Obtener datos de la guía
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        if request.method == 'POST':
            tipo_pesaje = request.form.get('tipo_pesaje')
            peso_bruto = request.form.get('peso_bruto')
            
            # Guardar datos de pesaje
            session['peso_bruto'] = peso_bruto
            session['tipo_pesaje'] = tipo_pesaje
            session['fecha_pesaje'] = datetime.now().strftime("%Y-%m-%d")
            session['hora_pesaje'] = datetime.now().strftime("%H:%M:%S")
            
            # Actualizar estado
            actualizar_estado_guia(codigo, {
                'estado': 'pesaje_completado',
                'peso_bruto': peso_bruto,
                'tipo_pesaje': tipo_pesaje
            })
            
            return redirect(url_for('ver_guia', codigo=codigo))
            
        # Renderizar template de pesaje
        return render_template('pesaje.html', 
                            codigo=codigo,
                            datos=datos_guia)
                            
    except Exception as e:
        logger.error(f"Error en pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje"), 500

@app.route('/procesar_pesaje_directo', methods=['POST'])
def procesar_pesaje_directo():
    try:
        if 'foto' not in request.files:
            return jsonify({'success': False, 'message': 'No se encontró la imagen'})
        
        foto = request.files['foto']
        codigo = request.form.get('codigo')
        
        if not foto:
            return jsonify({'success': False, 'message': 'Archivo no válido'})
            
        # Guardar la imagen temporalmente
        filename = secure_filename(foto.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        foto.save(temp_path)
        
        # Enviar al webhook de Make para procesamiento
        with open(temp_path, 'rb') as f:
            response = requests.post(
                PESAJE_WEBHOOK_URL,
                files={'file': (filename, f, 'image/jpeg')},
                data={'codigo': codigo}
            )
        
        # Procesar respuesta del webhook
        if response.status_code == 200:
            response_text = response.text
            
            if "Exitoso!" in response_text:
                import re
                peso_match = re.search(r'El peso bruto es: (\d+\.?\d*)', response_text)
                if peso_match:
                    peso = peso_match.group(1)
                    fecha_hora_actual = datetime.now()
                    
                    # Guardar nombre de la imagen
                    session['imagen_pesaje'] = filename
                    
                    # Generar PDF de pesaje
                    pdf_pesaje = generar_pdf_pesaje(
                        codigo=codigo,
                        peso_bruto=peso,
                        tipo_pesaje='directo',
                        imagen_peso=filename
                    )
                    
                    # Registrar en Make.com
                    registro_response = requests.post(
                        REGISTRO_PESO_WEBHOOK_URL,
                        json={
                            'codigo': codigo,
                            'peso_bruto': peso,
                            'tipo_pesaje': 'directo',
                            'fecha': fecha_hora_actual.strftime("%Y-%m-%d"),
                            'hora': fecha_hora_actual.strftime("%H:%M:%S")
                        }
                    )
                    
                    if registro_response.status_code != 200:
                        return jsonify({
                            'success': False,
                            'message': 'Error registrando el peso en el sistema'
                        })
                    
                    # Construir datos completos para guardar
                    datos_pesaje = {
                        'estado': 'pesaje_completado',
                        'estado_actual': 'pesaje_completado',
                        'peso_bruto': peso,
                        'tipo_pesaje': 'directo',
                        'fecha_pesaje': fecha_hora_actual.strftime("%Y-%m-%d"),
                        'hora_pesaje': fecha_hora_actual.strftime("%H:%M:%S"),
                        'pdf_pesaje': pdf_pesaje,
                        'imagen_pesaje': filename,
                        'codigo_guia': f"{codigo}_{fecha_hora_actual.strftime('%Y%m%d_%H%M%S')}"
                    }
                    
                    # Guardar en sesión
                    session.update(datos_pesaje)
                    
                    # Actualizar estado en la guía
                    actualizar_estado_guia(codigo, datos_pesaje)
                    
                    logger.info(f"Estado actualizado para guía {codigo}: {datos_pesaje}")
                    
                    return jsonify({
                        'success': True,
                        'peso': peso,
                        'message': 'Peso procesado correctamente'
                    })
                    
                else:
                    return jsonify({
                        'success': False,
                        'message': 'No se pudo extraer el peso de la respuesta'
                    })
            else:
                return jsonify({
                    'success': False,
                    'message': 'El código no corresponde a la guía'
                })
        else:
            return jsonify({
                'success': False,
                'message': 'Error procesando la imagen'
            })
            
    except Exception as e:
        logger.error(f"Error en pesaje directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

@app.route('/solicitar_autorizacion_pesaje', methods=['POST'])
def solicitar_autorizacion_pesaje():
    """
    Procesa la solicitud de autorización para pesaje virtual
    """
    try:
        data = request.get_json()
        codigo = data.get('codigo')
        comentarios = data.get('comentarios')
        
        if not codigo or not comentarios:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Generar código aleatorio de 6 caracteres
        codigo_autorizacion = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Guardar código con expiración de 1 hora
        codigos_autorizacion[codigo] = {
            'codigo': codigo_autorizacion,
            'expiracion': datetime.now() + timedelta(hours=1)
        }
        
        # Enviar solicitud a Make
        response = requests.post(
            AUTORIZACION_WEBHOOK_URL,
            json={
                'codigo_guia': codigo,
                'comentarios': comentarios,
                'codigo_autorizacion': codigo_autorizacion
            }
        )
        
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'message': 'Error enviando la solicitud'
            })
            
    except Exception as e:
        logger.error(f"Error en solicitud de autorización: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

@app.route('/validar_codigo_autorizacion', methods=['POST'])
def validar_codigo_autorizacion():
    """
    Valida el código de autorización para pesaje virtual
    """
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo')
        codigo_autorizacion = data.get('codigoAutorizacion')
        
        if not codigo_guia or not codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Verificar código
        auth_data = codigos_autorizacion.get(codigo_guia)
        if not auth_data:
            return jsonify({
                'success': False,
                'message': 'No hay solicitud de autorización activa'
            })
            
        # Verificar expiración
        if datetime.now() > auth_data['expiracion']:
            codigos_autorizacion.pop(codigo_guia)
            return jsonify({
                'success': False,
                'message': 'El código ha expirado'
            })
            
        # Verificar código
        if auth_data['codigo'] != codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Código inválido'
            })
            
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error validando código: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})
    
def generar_pdf_pesaje(codigo, peso_bruto, tipo_pesaje, imagen_peso=None):
    try:
        datos_guia = obtener_datos_guia(codigo)
        
        # Preparar datos para el PDF
        fecha_actual = datetime.now()
        # Usar la fecha del registro en lugar de la fecha actual para el nombre del archivo
        fecha_registro = datos_guia.get('fecha_registro', '').replace('/', '-')
        
        datos_pdf = {
            'codigo': codigo,
            'nombre': datos_guia.get('nombre', ''),
            'peso_bruto': peso_bruto,
            'tipo_pesaje': tipo_pesaje,
            'fecha_pesaje': fecha_actual.strftime('%d/%m/%Y'),
            'hora_pesaje': fecha_actual.strftime('%H:%M:%S'),
            'fecha_generacion': fecha_actual.strftime('%d/%m/%Y'),
            'hora_generacion': fecha_actual.strftime('%H:%M:%S'),
            'imagen_peso': imagen_peso,
            'qr_filename': session.get('qr_filename')
        }
        
        # Generar PDF
        rendered = render_template('pesaje_pdf_template.html', **datos_pdf)
        pdf_filename = f"pesaje_{codigo}_{fecha_actual.strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        
        HTML(string=rendered, base_url=app.static_folder).write_pdf(pdf_path)
        logger.info(f"PDF de pesaje generado exitosamente: {pdf_filename}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error generando PDF de pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        return None    

@app.route('/registrar_peso_virtual', methods=['POST'])
def registrar_peso_virtual():
    try:
        data = request.get_json()
        codigo = data.get('codigo')
        peso = data.get('peso')
        
        if not codigo or not peso:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
        
        # Fecha y hora actual
        fecha_hora = datetime.now()
        
        # Generar PDF de pesaje
        pdf_filename = generar_pdf_pesaje(
            codigo=codigo,
            peso_bruto=peso,
            tipo_pesaje='virtual',
            imagen_peso=None
        )
        
        # Datos a guardar
        datos_pesaje = {
            'estado': 'pesaje_completado',
            'peso_bruto': peso,
            'tipo_pesaje': 'virtual',
            'fecha_pesaje': fecha_hora.strftime("%Y-%m-%d"),
            'hora_pesaje': fecha_hora.strftime("%H:%M:%S"),
            'pdf_pesaje': pdf_filename
        }
        
        # Guardar en sesión
        session.update(datos_pesaje)
        
        # Actualizar estado
        actualizar_estado_guia(codigo, datos_pesaje)
        
        logger.info(f"Estado actualizado para guía {codigo}: {datos_pesaje}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error registrando peso virtual: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

def obtener_datos_guia(codigo):
    """
    Obtiene los datos actuales de la guía usando los datos más recientes
    """
    try:
        # Obtener datos de la sesión
        parsed_data = session.get('parsed_data', {})
        revalidation_data = session.get('revalidation_data', {})
        image_filename = session.get('image_filename')

        # Fecha y hora actual
        now = datetime.now()
        
        # Datos básicos
        datos = {
            'codigo': codigo,
            'nombre': '',
            'fecha_registro': '',  # Se llenará con la fecha del tiquete
            'hora_registro': now.strftime("%H:%M:%S"),
            'placa': '',
            'transportador': '',
            'cantidad_racimos': '',
            'estado_actual': session.get('estado_actual', 'pesaje'),
            'image_filename': image_filename,
            'pdf_filename': session.get('pdf_filename', ''),
        }
        
        # Extraer datos del parsed_data
        if parsed_data and 'table_data' in parsed_data:
            for row in parsed_data['table_data']:
                campo = row['campo']
                valor = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                
                if campo == 'Fecha':
                    # Intentar diferentes formatos de fecha
                    try:
                        # Intenta formato dd-mm-yyyy
                        fecha_obj = datetime.strptime(valor, "%d-%m-%Y")
                        datos['fecha_registro'] = fecha_obj.strftime("%d/%m/%Y")
                    except ValueError:
                        try:
                            # Intenta formato yyyy-mm-dd
                            fecha_obj = datetime.strptime(valor, "%Y-%m-%d")
                            datos['fecha_registro'] = fecha_obj.strftime("%d/%m/%Y")
                        except ValueError:
                            datos['fecha_registro'] = valor
                elif campo == 'Nombre del Agricultor':
                    datos['nombre'] = valor
                elif campo == 'Código':
                    datos['codigo'] = valor
                elif campo == 'Placa':
                    datos['placa'] = valor
                elif campo == 'Cantidad de Racimos':
                    datos['cantidad_racimos'] = valor
                elif campo == 'Transportador':
                    datos['transportador'] = valor

        # Si no se encontró fecha, usar la fecha actual
        if not datos['fecha_registro']:
            datos['fecha_registro'] = now.strftime("%d/%m/%Y")
        
        logger.info(f"Datos obtenidos para guía {codigo}: {datos}")
        return datos
        
    except Exception as e:
        logger.error(f"Error obteniendo datos de guía: {str(e)}")
        logger.error(traceback.format_exc())
        return {}
    
def actualizar_estado_guia(codigo, datos):
    """
    Actualiza el estado y datos de la guía
    Por ahora guardamos en sesión, luego será en base de datos
    """
    try:
        # Actualizar datos en la sesión
        for key, value in datos.items():
            session[key] = value
            
        logger.info(f"Estado actualizado para guía {codigo}: {datos}")
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando estado de guía: {str(e)}")
        return False
    
@app.route('/ver_guia/<codigo>')
def ver_guia(codigo):
    """
    Muestra la vista actual de la guía
    """
    try:
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Generar código de guía con formato: codigo_fecha_hora
        now = datetime.now()
        fecha_hora = now.strftime("%Y%m%d_%H%M%S")
        
        # Formatear fecha para mostrar
        fecha_formato = now.strftime("%d/%m/%Y")
        
        # Actualizar datos_guia con el nuevo código y fecha
        datos_guia.update({
            'codigo_guia': f"{codigo}_{fecha_hora}",
            'fecha_formato': fecha_formato,
            'hora_formato': now.strftime("%H:%M:%S")
        })
            
        return render_template('guia_template.html', **datos_guia)
        
    except Exception as e:
        logger.error(f"Error mostrando guía: {str(e)}")
        return render_template('error.html', message="Error mostrando guía"), 500
    
@app.route('/notify-admin', methods=['POST'])
def notify_admin():
    try:
        data = request.get_json()
        
        # Preparar los datos para el webhook de notificación
        notification_data = {
            "codigo": data.get('codigo', ''),
            "nombre": data.get('nombre', ''),
            "nota": data.get('nota', ''),
            "fecha_notificacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tipo_error": "Validación fallida"
        }
        
        # Llamar al webhook de notificación
        response = requests.post(
            ADMIN_NOTIFICATION_WEBHOOK_URL,
            json=notification_data,
            headers={'Content-Type': 'application/json'}
        )
        
        logger.info(f"Notificación admin enviada: {response.status_code}")
        logger.info(f"Respuesta webhook: {response.text}")
        
        if response.status_code == 200:
            return jsonify({
                "status": "success",
                "message": "Administrador notificado exitosamente"
            })
        else:
            raise Exception(f"Error en webhook: {response.text}")
            
    except Exception as e:
        logger.error(f"Error notificando admin: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": f"Error al notificar: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
