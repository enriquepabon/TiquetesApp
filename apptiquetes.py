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
from utils import generate_pdf, generate_qr, get_drive_service, upload_to_drive
from parser import parse_markdown_response
from config import app

# Configuración de Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
    try:
        app.logger.info(f"Intentando servir archivo: {filename}")
        app.logger.info(f"Directorio de guías: {app.config['GUIAS_FOLDER']}")
        app.logger.info(f"¿Archivo existe? {os.path.exists(os.path.join(app.config['GUIAS_FOLDER'], filename))}")
        
        return send_from_directory(app.config['GUIAS_FOLDER'], filename)
    except Exception as e:
        app.logger.error(f"Error sirviendo archivo: {str(e)}")
        return render_template('error.html', message="Archivo no encontrado"), 404

# URLs de los Webhooks en Make.com
PROCESS_WEBHOOK_URL = "https://hook.us2.make.com/asrfb3kv3cw4o4nd43wylyasfx5yq55f"
REGISTER_WEBHOOK_URL = "https://hook.us2.make.com/f63o7rmsuixytjfqxq3gjljnscqhiedl"
REVALIDATION_WEBHOOK_URL = "https://hook.us2.make.com/bok045bvtwpj89ig58nhrmx1x09yh56u"

# Extensiones permitidas para subir
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            image_filename = secure_filename(file.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            file.save(image_path)
            session['image_filename'] = image_filename
            return redirect(url_for('processing'))
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
        generate_qr(qr_data, qr_path)
        
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
        data = request.get_json()
        logger.info(f"Datos recibidos en register: {data}")
        
        parsed_data = session.get('parsed_data', {})
        image_filename = session.get('image_filename', '')
        
        logger.info(f"Datos de sesión - parsed_data: {parsed_data}")
        logger.info(f"Datos de sesión - image_filename: {image_filename}")
        
        if not parsed_data or not image_filename:
            logger.error("Faltan datos necesarios para el registro")
            return jsonify({
                "status": "error",
                "message": "No hay datos para registrar."
            }), 400

        # Obtener fecha del tiquete original
        fecha_tiquete = None
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_tiquete = row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
                break
        
        # Si no hay fecha en el tiquete, usar la fecha actual
        if not fecha_tiquete or fecha_tiquete == 'No disponible':
            fecha_tiquete = datetime.now().strftime("%Y-%m-%d")
        
        fecha_procesamiento = fecha_tiquete
        hora_procesamiento = datetime.now().strftime("%H:%M:%S")
        
        # Extraer todos los datos actualizados
        revalidation_data = {}
        for row in parsed_data.get('table_data', []):
            campo = row['campo']
            valor = row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
            revalidation_data[campo] = valor

        # Agregar datos de revalidación recibidos
        if data.get('Nombre'):
            revalidation_data['Nombre del Agricultor'] = data['Nombre']
        if data.get('Codigo'):
            revalidation_data['Código'] = data['Codigo']
        if data.get('Nota'):
            revalidation_data['nota'] = data['Nota']
        
        logger.info(f"Datos de revalidación completos: {revalidation_data}")
        
        try:
            # Generar PDF con todos los datos
            pdf_filename = generate_pdf(
                parsed_data=parsed_data,
                image_filename=image_filename,
                fecha_procesamiento=fecha_procesamiento,
                hora_procesamiento=hora_procesamiento,
                revalidation_data=revalidation_data
            )
            
            # Guardar todos los datos actualizados en la sesión
            session['pdf_filename'] = pdf_filename
            session['revalidation_data'] = revalidation_data
            session['estado_actual'] = 'pesaje'
            
            logger.info(f"PDF generado y datos guardados: {pdf_filename}")
            
            return jsonify({
                "status": "success",
                "message": "Registro completado exitosamente",
                "pdf_filename": pdf_filename
            })
            
        except Exception as pdf_error:
            logger.error(f"Error generando PDF: {str(pdf_error)}")
            logger.error(traceback.format_exc())
            return jsonify({
                "status": "error",
                "message": f"Error generando documentos: {str(pdf_error)}"
            }), 500
            
    except Exception as e:
        logger.error(f"Error general en registro: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": f"Error al registrar: {str(e)}"
        }), 500
    
@app.route('/review_pdf', methods=['GET'])
def review_pdf():
    """
    Muestra una página con el enlace (o vista) del PDF generado.
    No se descarga automáticamente, sino que se guardó en 'pdfs/'.
    """
    pdf_filename = session.get('pdf_filename')
    if not pdf_filename:
        return render_template('error.html', message="No se encontró el PDF generado.")
    
    pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
    if not os.path.exists(pdf_path):
        return render_template('error.html', message="El PDF no está disponible.")
    
    return render_template('review_pdf.html', pdf_filename=pdf_filename)

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
    try:
        # Obtener datos actuales de la guía
        datos_guia = obtener_datos_guia(codigo)  # Necesitarás implementar esta función
        
        if request.method == 'POST':
            peso_bruto = request.form.get('peso_bruto')
            tipo_pesaje = request.form.get('tipo_pesaje')
            # Guardar datos de pesaje
            actualizar_estado_guia(codigo, {
                'peso_bruto': peso_bruto,
                'tipo_pesaje': tipo_pesaje,
                'hora_pesaje': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'estado_actual': 'clasificacion'
            })
            return redirect(url_for('ver_guia', codigo=codigo))
            
        return render_template(
            'pesaje.html',
            codigo=codigo,
            datos=datos_guia
        )
    except Exception as e:
        app.logger.error(f"Error en pesaje: {str(e)}")
        return render_template('error.html', message="Error procesando pesaje"), 500
    
    # En apptiquetes.py, agrega estas funciones

def obtener_datos_guia(codigo):
    """
    Obtiene los datos actuales de la guía usando los datos más recientes
    """
    try:
        parsed_data = session.get('parsed_data', {})
        revalidation_data = session.get('revalidation_data', {})
        
        # Extraer datos del parsed_data
        table_data = parsed_data.get('table_data', [])
        datos = {}
        for row in table_data:
            campo = row['campo']
            # Usar valor sugerido a menos que sea 'No disponible'
            valor = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
            
            # Mapear campos a datos
            if campo == 'Fecha':
                datos['fecha'] = valor
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
        
        # Sobrescribir con datos de revalidación si existen
        if revalidation_data:
            if 'Nombre del Agricultor' in revalidation_data:
                datos['nombre'] = revalidation_data['Nombre del Agricultor']
            if 'Código' in revalidation_data:
                datos['codigo'] = revalidation_data['Código']

        # Construir estructura final
        datos_guia = {
            'codigo': datos.get('codigo', codigo),
            'nombre': datos.get('nombre', ''),
            'fecha_registro': datos.get('fecha', datetime.now().strftime("%d-%m-%Y")),
            'placa': datos.get('placa', ''),
            'transportador': datos.get('transportador', ''),
            'cantidad_racimos': datos.get('cantidad_racimos', ''),
            'estado_actual': session.get('estado_actual', 'pesaje'),
            'image_filename': session.get('image_filename', ''),
            'pdf_filename': session.get('pdf_filename', ''),
        }
        
        logger.info(f"Datos obtenidos para guía {codigo}: {datos_guia}")
        return datos_guia
        
    except Exception as e:
        logger.error(f"Error obteniendo datos de guía: {str(e)}")
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
            
        return render_template('guia_template.html', **datos_guia)
        
    except Exception as e:
        logger.error(f"Error mostrando guía: {str(e)}")
        return render_template('error.html', message="Error mostrando guía"), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
