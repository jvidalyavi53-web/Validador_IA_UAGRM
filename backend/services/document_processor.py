import os
import io
import re
import logging

import fitz
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Procesa PDFs: extrae texto nativo y, si la página parece escaneada, aplica
    OCR con Tesseract. Si Tesseract no está disponible, continúa sin OCR
    (las páginas escaneadas quedarán vacías, no se cuelga).
    """

    def __init__(self, tesseract_cmd_path: str = None) -> None:
        self.ocr_enabled = True
        if tesseract_cmd_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd_path
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract disponible: {version}")
        except Exception as exc:
            self.ocr_enabled = False
            logger.warning(
                f"Tesseract NO disponible ({exc}). OCR deshabilitado; "
                "solo se procesará texto nativo de PDFs."
            )

    def clean_ocr_text(self, text: str) -> str:
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

                text = page.get_text() or ""

                if len(text.strip()) < 50:
                    if not self.ocr_enabled:
                        text_content.append(
                            "[Página escaneada omitida: Tesseract no instalado]"
                        )
                    else:
                        try:
                            mat = fitz.Matrix(3, 3)
                            pix = page.get_pixmap(matrix=mat)
                            img = Image.open(io.BytesIO(pix.tobytes()))
                            text = pytesseract.image_to_string(img, lang="spa")
                        except Exception as ocr_exc:
                            logger.warning(
                                f"OCR falló en página {page_num + 1}: {ocr_exc}"
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
            logger.error(f"Error procesando el PDF: {exc}")
            raise RuntimeError(f"No se pudo procesar el PDF: {exc}") from exc
