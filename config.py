from flask import Flask

app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER='static/uploads',
    PDF_FOLDER='static/pdfs',
    SECRET_KEY='tu_clave_secreta'  # Cambia esto
)
# config.py
app.config['SERVER_NAME'] = 'localhost:5002'  # O tu dominio en producción
# Crear directorios si no existen
import os
for folder in [app.config['UPLOAD_FOLDER'], app.config['PDF_FOLDER']]:
    os.makedirs(folder, exist_ok=True)