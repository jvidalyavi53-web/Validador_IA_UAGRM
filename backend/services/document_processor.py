import os
import io
import re
import logging
from typing import Optional, Any

import fitz
from PIL import Image

logger = logging.getLogger(__name__)


class _BaseOCR:
    """Interfaz común: extract_text(pil_image) -> str"""

    name: str = "base"
    enabled: bool = True

    def extract_text(self, img: Image.Image, lang: str = "es") -> str:
        raise NotImplementedError


class _TesseractOCR(_BaseOCR):
    def __init__(self, tesseract_cmd: Optional[str] = None) -> None:
        self.name = "tesseract"
        try:
            import pytesseract

            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            pytesseract.get_tesseract_version()
            self._pytesseract = pytesseract
            logger.info("OCR engine: Tesseract (binario nativo)")
        except Exception as exc:
            self.enabled = False
            self._error = exc
            logger.warning(f"Tesseract NO disponible ({exc}); se buscará RapidOCR.")

    def extract_text(self, img: Image.Image, lang: str = "es") -> str:
        if not self.enabled:
            return ""
        lang_map = {"es": "spa", "en": "eng"}
        return self._pytesseract.image_to_string(img, lang=lang_map.get(lang, "spa"))


class _RapidOCR(_BaseOCR):
    """OCR 100% Python (modelos ONNX). No requiere binarios del sistema."""

    def __init__(self) -> None:
        self.name = "rapidocr"
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            self._engine = RapidOCR()
            self.enabled = True
            logger.info("OCR engine: RapidOCR (ONNX, pure-Python).")
        except Exception as exc:
            self.enabled = False
            self._error = exc
            logger.warning(
                f"RapidOCR NO disponible ({exc}); OCR deshabilitado por completo."
            )

    def extract_text(self, img: Image.Image, lang: str = "es") -> str:
        if not self.enabled:
            return ""
        import numpy as np

        arr = np.array(img.convert("RGB"))
        result, _elapse = self._engine(arr)
        if not result:
            return ""
        return "\n".join([line[1] for line in result if line and len(line) > 1])


class DocumentProcessor:
    """
    Procesa PDFs: extrae texto nativo y, si la página parece escaneada,
    aplica OCR. Soporta Tesseract (si el binario está) o RapidOCR (pure-Python).
    Si ninguno está disponible, las páginas escaneadas se omiten sin tirar la app.
    """

    def __init__(self, tesseract_cmd_path: Optional[str] = None) -> None:
        # Prioridad 1: Tesseract (si el binario existe en el sistema)
        self._ocr_backends: list[_BaseOCR] = []
        tess = _TesseractOCR(tesseract_cmd_path)
        if tess.enabled:
            self._ocr_backends.append(tess)

        # Prioridad 2: RapidOCR (pure-Python, siempre disponible si está instalado)
        rapid = _RapidOCR()
        if rapid.enabled:
            self._ocr_backends.append(rapid)

        if not self._ocr_backends:
            logger.warning(
                "Ningún motor OCR disponible. Solo se procesará texto nativo de PDFs."
            )
        else:
            logger.info(
                f"OCR chain (en orden de intento): "
                f"{[b.name for b in self._ocr_backends]}"
            )

        self.ocr_enabled: bool = bool(self._ocr_backends)

    def _ocr_with_fallback(self, img: Image.Image) -> str:
        """Prueba cada backend en orden; devuelve el primer resultado no vacío."""
        for backend in self._ocr_backends:
            try:
                text = backend.extract_text(img, lang="es")
                if text and text.strip():
                    return text
            except Exception as exc:
                logger.warning(f"OCR backend {backend.name} falló: {exc}")
        return ""

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
                            "[Página escaneada omitida: ningún motor OCR disponible]"
                        )
                    else:
                        try:
                            mat = fitz.Matrix(3, 3)
                            pix = page.get_pixmap(matrix=mat)
                            img = Image.open(io.BytesIO(pix.tobytes()))
                            text = self._ocr_with_fallback(img)
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
