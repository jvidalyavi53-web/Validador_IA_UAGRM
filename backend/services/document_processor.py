import os
import logging
from typing import Optional
from dotenv import load_dotenv
from llama_parse import LlamaParse

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """
    Procesa PDFs usando LlamaParse. 
    Reemplaza la antigua lógica mixta (PyMuPDF + Mindee) por un motor unificado 
    de IA que extrae texto nativo, realiza OCR a las imágenes y estructura 
    las tablas legalmente en formato Markdown.
    """

    def __init__(self, tesseract_cmd_path: Optional[str] = None) -> None:
        load_dotenv()
        # Buscamos la llave de LlamaCloud en Render o en tu archivo .env local
        self.api_key = os.getenv("LLAMA_CLOUD_API_KEY")
        
        if not self.api_key:
            logger.error("ALERTA CRÍTICA: LLAMA_CLOUD_API_KEY no encontrada en el entorno.")
            
        # Inicializamos el motor LlamaParse
        # result_type="markdown" es clave para que las tablas no se rompan
        self.parser = LlamaParse(
            api_key=self.api_key,
            result_type="markdown",
            verbose=True,
            language="es",
            num_workers=2
        )

    def process_pdf(
        self,
        file_path: str,
        progress_callback=None,  # Se mantiene por compatibilidad con tu arquitectura
    ) -> str:
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo {file_path} no existe.")

        if not self.api_key:
            raise ValueError("Falta LLAMA_CLOUD_API_KEY. Configúrala en Render.")

        try:
            logger.info(f"Delegando PDF a LlamaParse Cloud: {file_path}")
            
            # La magia: load_data procesa el documento entero (OCR y texto nativo) de una sola vez
            documents = self.parser.load_data(file_path)
            
            if not documents:
                logger.warning("LlamaParse procesó el documento pero devolvió texto vacío.")
                return ""

            # LlamaParse devuelve una lista de objetos, los unimos todos en un solo texto
            texto_completo = "\n\n".join([doc.text for doc in documents])
            
            # Simulamos el callback al 100% por si alguna otra parte de tu código lo espera
            if progress_callback:
                progress_callback(1, 1)

            logger.info(f"Extracción exitosa. {len(texto_completo)} caracteres obtenidos.")
            return texto_completo

        except Exception as exc:
            logger.error(f"Fallo crítico en LlamaParse: {exc}")
            raise RuntimeError(f"Error procesando PDF con LlamaParse: {exc}") from exc