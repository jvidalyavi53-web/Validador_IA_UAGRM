import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import os
import logging
import re

logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self, tesseract_cmd_path: str = None):
        if tesseract_cmd_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd_path
            
    def clean_ocr_text(self, text: str) -> str:
        """Limpia la basura visual básica del escáner"""
        text = re.sub(r'\n+', '\n', text)  # Quita saltos de línea excesivos
        text = re.sub(r' +', ' ', text)    # Quita espacios dobles
        return text

    def process_pdf(self, file_path: str, progress_callback=None) -> str:
        """Extrae texto con OCR de ALTA RESOLUCIÓN para PDFs escaneados."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo {file_path} no existe.")

        text_content = []
        try:
            pdf_document = fitz.open(file_path)
            total_pages = len(pdf_document)
            logger.info(f"Procesando normativa pesada: {total_pages} páginas.")

            for page_num in range(total_pages):
                page = pdf_document[page_num]
                text_content.append(f"\n[--- INICIO PÁGINA {page_num + 1} ---]\n")

                text = page.get_text()
                
                # Si la página es escaneada (tiene menos de 50 caracteres puros)
                if len(text.strip()) < 50:
                    # ⚠️ MAGIA: Zoom 3x para que Tesseract lea en 300 DPI
                    mat = fitz.Matrix(3, 3) 
                    pix = page.get_pixmap(matrix=mat)
                    img = Image.open(io.BytesIO(pix.tobytes()))
                    
                    # Forzamos estrictamente el idioma español
                    text = pytesseract.image_to_string(img, lang='spa')
                
                # Limpiamos el texto antes de guardarlo
                text = self.clean_ocr_text(text)
                
                text_content.append(text)
                text_content.append(f"\n[--- FIN PÁGINA {page_num + 1} ---]\n")

                if progress_callback:
                    progress_callback(page_num + 1, total_pages)

            pdf_document.close()
            return "".join(text_content)
        except Exception as e:
            logger.error(f"Error procesando el PDF: {e}")
            raise e