from flask import Flask, render_template, request, redirect, url_for, session, jsonify
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
from utils import generate_pdf
from utils import generate_qr, get_drive_service, upload_to_drive
from config import app
from utils import generate_pdf, generate_qr


# Agregar/modificar la ruta register con el código que proporcioné

# >>> NUEVO: librerías para QR y Excel (opcionales si necesitas)
try:
    import magic
    HAVE_MAGIC = True
except ImportError:
    HAVE_MAGIC = False

from parser import parse_markdown_response

# >>> NUEVO:
import qrcode
from io import BytesIO
from PIL import Image
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as ExcelImage

app = Flask(__name__)

# Configuración de Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Clave secreta para usar sesiones (cámbiala por una clave segura en producción)
app.secret_key = 'tu_clave_secreta_aquí'

# Directorio para guardar las imágenes y PDFs dentro de static
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
PDF_FOLDER = os.path.join(app.static_folder, 'pdfs')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PDF_FOLDER'] = PDF_FOLDER

# >>> NUEVO: carpeta para Excel (si quieres guardar un archivo local)
EXCEL_FOLDER = os.path.join(app.static_folder, 'excels')
os.makedirs(EXCEL_FOLDER, exist_ok=True)

# URLs de los Webhooks en Make.com
PROCESS_WEBHOOK_URL = "https://hook.us2.make.com/asrfb3kv3cw4o4nd43wylyasfx5yq55f"
REGISTER_WEBHOOK_URL = "https://hook.us2.make.com/f63o7rmsuixytjfqxq3gjljnscqhiedl"
# URL del nuevo webhook para revalidación
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
        logger.info(f"Datos recibidos: {updated_data}")
        
        table_data = updated_data.get('table_data', [])
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
                        # Intentar parsear la respuesta como JSON
                        webhook_data = response.json()
                    except ValueError:
                        # Si no es JSON válido, intentar parsear el texto estructurado
                        webhook_text = response.text
                        if isinstance(webhook_text, str):
                            # Parsear la respuesta estructurada
                            lines = webhook_text.split('\n')
                            webhook_data = {
                                'Body': {
                                    'Resultado': next((l.replace('Resultado:', '').strip() for l in lines if 'Resultado:' in l), ''),
                                    'Codigo': next((l.replace('Codigo:', '').strip().strip('"') for l in lines if 'Codigo:' in l), ''),
                                    'Nombre': next((l.replace('Nombre:', '').strip().strip('"') for l in lines if 'Nombre:' in l), ''),
                                    'Nota': next((l.replace('Nota:', '').strip() for l in lines if 'Nota:' in l), '')
                                },
                                'Status': response.status_code
                            }

                    # Estructurar la respuesta final
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
                else:
                    raise Exception(f"Error en webhook: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error en petición al webhook: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": f"Error de conexión: {str(e)}"
                }), 500
            except Exception as e:
                logger.error(f"Error procesando respuesta: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": str(e)
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
        
        now = datetime.now()
        fecha_emision = now.strftime("%Y-%m-%d")
        hora_emision = now.strftime("%H:%M:%S")
        
        # Generar QR con los datos validados
        qr_data = {
            "codigo": revalidation_data.get('Código') if revalidation_data else parsed_data.get('codigo', ''),
            "nombre": revalidation_data.get('Nombre del Agricultor') if revalidation_data else parsed_data.get('nombre_agricultor', ''),
            "fecha": fecha_procesamiento
        }
        
        qr_filename = f"qr_{qr_data['codigo']}_{int(time.time())}.png"
        qr_path = os.path.join(app.static_folder, qr_filename)
        generate_qr(str(qr_data), qr_path)
        
        # Renderizar la plantilla HTML
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
        
        # Generar el PDF
        pdf_filename = f'tiquete_{qr_data["codigo"]}_{fecha_procesamiento}.pdf'
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
        logger.info(f"Datos recibidos: {data}")
        
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

        now = datetime.now()
        fecha_procesamiento = now.strftime("%Y-%m-%d")
        hora_procesamiento = now.strftime("%H:%M:%S")
        
        # Preparar datos de revalidación
        revalidation_data = {
            'Nombre del Agricultor': data.get('Nombre', ''),
            'Código': data.get('Codigo', ''),
            'nota': data.get('Nota', '')
        }
        
        logger.info(f"Datos de revalidación preparados: {revalidation_data}")
        
        try:
            # Generar PDF
            pdf_filename = generate_pdf(
                parsed_data=parsed_data,
                image_filename=image_filename,
                fecha_procesamiento=fecha_procesamiento,
                hora_procesamiento=hora_procesamiento,
                revalidation_data=revalidation_data
            )
            
            logger.info(f"PDF generado exitosamente: {pdf_filename}")
            
            # Guardar el nombre del PDF en la sesión
            session['pdf_filename'] = pdf_filename
            
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

if __name__ == '__main__':
    app.run(debug=True, port=5002)
