import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.document_processor import DocumentProcessor
from backend.services.text_chunker import TextChunker
from backend.database.vector_db import VectorDB

# Configuración
ruta_tesseract = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
nombre_archivo = "descarga 2026..pdf"
ruta_pdf = os.path.join("data", nombre_archivo) # OJO: Si falló antes, prueba "data" o "..data"

# Inicializar todo
procesador = DocumentProcessor(tesseract_cmd_path=ruta_tesseract)
chunker = TextChunker()
vdb = VectorDB(db_path="data/chroma_db") # Se creará esta carpeta

try:
    print("\n--- PASO 1: PROCESANDO DOCUMENTO ---")
    texto = procesador.process_pdf(ruta_pdf)
    fragmentos = chunker.split_text(texto, document_name=nombre_archivo)
    
    print("\n--- PASO 2: GUARDANDO EN BASE DE DATOS VECTORIAL ---")
    vdb.add_documents(fragmentos)
    
    print("\n--- PASO 3: PRUEBA DE BÚSQUEDA ---")
    pregunta = "Zenobia Yavi Cahuana" # Algo que sabemos que está en tu PDF
    resultados = vdb.search(pregunta)
    
    print(f"\nPregunta: {pregunta}")
    print("Resultado más parecido encontrado:")
    print(resultados['documents'][0][0][:300], "...")
    
except Exception as e:
    print(f"\nError: {e}")