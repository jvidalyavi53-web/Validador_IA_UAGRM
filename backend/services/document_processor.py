import os
import io
import re
import logging
from typing import Optional
import requests

import fitz
from PIL import Image

logger = logging.getLogger(__name__)

class _MindeeOCR:
    """Motor OCR en la nube usando Mindee API para liberar la RAM del servidor local."""

    def __init__(self, api_key: str) -> None:
        self.name = "mindee"
        self.api_key = api_key
        self.enabled = bool(api_key)
        if self.enabled:
            logger.info("OCR engine: Mindee Cloud API (Activo)")
        else:
            logger.warning("Mindee API key no proporcionada. OCR deshabilitado.")

    def extract_text(self, img: Image.Image, lang: str = "es") -> str:
        if not self.enabled:
            return ""

        url = "https://api.mindee.net/v1/products/mindee/doctr/v1/predict"
        headers = {"Authorization": f"Token {self.api_key}"}

        # Convertir PIL Image a bytes para enviarlo por HTTP
        img_byte_arr = io.BytesIO()
        # Guardamos la imagen en formato JPEG con calidad 85 para hacer la transferencia rapidísima
        img.save(img_byte_arr, format='JPEG', quality=85)
        img_byte_arr.seek(0)

        files = {"document": ("page.jpg", img_byte_arr, "image/jpeg")}

        try:
            # Enviamos la imagen a los servidores de Mindee
            response = requests.post(url, files=files, headers=headers, timeout=45)
            response.raise_for_status()
            data = response.json()

            texto_completo = ""
            # Recorremos la estructura JSON que devuelve Mindee para armar las oraciones
            pages = data.get('document', {}).get('inference', {}).get('pages', [])
            for page in pages:
                words = page.get('prediction', {}).get('words', [])
                for word in words:
                    texto_completo += word.get('text', '') + " "
                texto_completo += "\n"

            return texto_completo.strip()
            
        except requests.exceptions.Timeout:
            logger.error("Mindee API tardó demasiado en responder (Timeout).")
            return ""
        except Exception as exc:
            logger.error(f"Fallo en la conexión con Mindee API: {exc}")
            return ""


class DocumentProcessor:
    """
    Procesa PDFs: extrae texto nativo de manera inmediata y, si detecta una página 
    escaneada (sin texto nativo), delega el esfuerzo del OCR externo a la API de Mindee 
    para no saturar la memoria RAM del entorno host (ej. Render).
    """

    def __init__(self, tesseract_cmd_path: Optional[str] = None) -> None:
        # Extraemos la llave desde las variables de entorno por seguridad, 
        # pero inyectamos tu llave de Mindee como valor por defecto (Fallback).
        api_key = os.getenv("MINDEE_API_KEY", "md_LbpfP3nYfIyfcLL627uWmDSbU7B5DGhOjM2obhEWaeQ")
        
        self._ocr_engine = _MindeeOCR(api_key=api_key)
        self.ocr_enabled: bool = self._ocr_engine.enabled

        if not self.ocr_enabled:
            logger.warning("Ningún motor OCR Cloud disponible. Solo se procesará texto nativo.")

    def clean_ocr_text(self, text: str) -> str:
        # Limpieza básica de saltos de línea y espacios múltiples
        text = re.sub(r"\n+", "\n", text)
        text = re.sub(r" +", " ", text)
        return text

    def process_pdf(
        self,
        file_path: str,
        progress_callback=None,
    ) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo {file_path} no existe.")

        text_content: list[str] = []
        try:
            pdf_document = fitz.open(file_path)
            total_pages = len(pdf_document)
            logger.info(f"Procesando PDF: {total_pages} páginas.")

            for page_num in range(total_pages):
                page = pdf_document[page_num]
                text_content.append(
                    f"\n[--- INICIO PÁGINA {page_num + 1} ---]\n"
                )

                # Intento 1: Extracción limpia (Documentos nativos)
                text = page.get_text() or ""

                # Intento 2: Si el texto extraído es mínimo (< 50 caracteres), asumimos que es una imagen escaneada
                if len(text.strip()) < 50:
                    if not self.ocr_enabled:
                        text_content.append(
                            "[Página escaneada omitida: motor OCR Cloud deshabilitado]"
                        )
                    else:
                        try:
                            logger.info(f"Página {page_num + 1} escaneada. Enviando a los servidores de Mindee...")
                            
                            # Corrección clave: Extraer el pixmap usando dpi directamente, sin Matrix
                            pix = page.get_pixmap(dpi=150)
                            img = Image.open(io.BytesIO(pix.tobytes()))
                            
                            # La magia: Delegamos el trabajo al motor externo
                            text = self._ocr_engine.extract_text(img)
                        except Exception as ocr_exc:
                            logger.warning(
                                f"OCR de Mindee falló en la página {page_num + 1}: {ocr_exc}"
                            )
                            text = ""

                text = self.clean_ocr_text(text)
                text_content.append(text)
                text_content.append(
                    f"\n[--- FIN PÁGINA {page_num + 1} ---]\n"
                )

                if progress_callback:
                    progress_callback(page_num + 1, total_pages)

            pdf_document.close()
            return "".join(text_content)
        except Exception as exc:
            logger.error(f"Error crítico procesando el PDF: {exc}")
            raise RuntimeError(f"No se pudo procesar el PDF: {exc}") from exc