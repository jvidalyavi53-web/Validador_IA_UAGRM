import os
import re
import logging
from typing import Tuple
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UAGRM_RAGEngine")

load_dotenv()

class IntentRouter:
    """Arquitectura de Enrutamiento Semántico para Validaciones."""
    @staticmethod
    def detect_intent(query: str) -> str:
        query_cleaned = query.lower().strip()
        audit_patterns = [
            r"\bvalidar\b", r"\bresolución\b", r"\bresolucion\b", 
            r"\baprobar\b", r"\bevaluar\b", r"\bauditar\b", r"\bdictaminar\b"
        ]
        if any(re.search(pattern, query_cleaned) for pattern in audit_patterns):
            return "JUEZ_NORMATIVO"
        return "ASESOR_ACADEMICO"

class RAGEngine:
    """Motor Core de Recuperación Aumentada."""
    def __init__(self, vdb_instance, provider="groq"):
        self.vdb = vdb_instance
        self.provider = provider
        self.llm = self._initialize_llm()

    def _initialize_llm(self):
        if self.provider == "groq":
            return ChatGroq(
                temperature=0.01,
                model_name="llama-3.3-70b-versatile",
                api_key=os.getenv("GROQ_API_KEY"),
                max_tokens=2048
            )
        else:
            return ChatOllama(
                model="llama3", 
                temperature=0.1,     
                num_predict=1024,     
                repeat_penalty=1.25 # Prevención crítica de Model Collapse
            )

    def _build_prompts(self, intent: str, context: str) -> Tuple[str, str]:
        """Técnica de Prompt Sandwiching para evitar Prompt Leakage."""
        if intent == "JUEZ_NORMATIVO":
            system_prompt = (
                "ACTÚAS EXCLUSIVAMENTE COMO: Juez Normativo de la Universidad Autónoma Gabriel René Moreno (UAGRM).\n"
                "MISIÓN: Realizar auditoría jurídica de la propuesta frente al Corpus Normativo.\n\n"
                "REGLAS CRÍTICAS:\n"
                "1. INICIA EXCLUSIVAMENTE CON: **APROBADO** o **OBSERVADO**.\n"
                "2. NO saludes ni te despidas.\n"
                "3. EL SUSTENTO LEGAL DEBE CITAR EXACTAMENTE: [Artículo] y [Documento Fuente].\n"
                "4. FILTRO OCR: Ignora basura del escáner.\n"
                "5. PROTOCOLO DE RECHAZO: Si el documento es código o irrelevante, dictamina 'OBSERVADO'.\n\n"
                "<CORPUS_NORMATIVO>\n{context}\n</CORPUS_NORMATIVO>"
            )
            human_reinforcement = (
                "PROPUESTA A EVALUAR:\n{query}\n\n"
                "INSTRUCCIÓN FINAL: Ejecuta auditoría. Inicia con **APROBADO/OBSERVADO** y provee Sustento Legal."
            )
        else:
            system_prompt = (
                "ACTÚAS EXCLUSIVAMENTE COMO: Asesor Académico Institucional de la UAGRM.\n"
                "MISIÓN: Proveer información estructurada basada en el Corpus Documental.\n\n"
                "REGLAS:\n"
                "1. Tu tono es institucional y directo.\n"
                "2. Usa listas (viñetas) si se piden múltiples elementos.\n"
                "3. Cita el documento de origen.\n"
                "4. NO inventes información.\n\n"
                "<CORPUS_DOCUMENTAL>\n{context}\n</CORPUS_DOCUMENTAL>"
            )
            human_reinforcement = (
                "CONSULTA DEL USUARIO:\n{query}\n\n"
                "INSTRUCCIÓN FINAL: Responde con claridad y estructura profesional basada en el contexto."
            )
        return system_prompt, human_reinforcement

    def ask(self, query: str) -> str:
        try:
            search_results = self.vdb.search(query, n_results=10) 
            if not search_results['documents'] or not search_results['documents'][0]:
                return "**OBSERVADO**\n\nRAM Vectorial vacía. Ingrese los documentos PDF en la Biblioteca Institucional."
                
            context_pieces = []
            fuentes_unicas = set() #  FASE 5: Recolector de Trazabilidad
            
            for doc, meta in zip(search_results['documents'][0], search_results['metadatas'][0]):
                source = meta.get('source', 'Documento_Desconocido')
                fuentes_unicas.add(source) # Guardamos el nombre del PDF sin repetir
                context_pieces.append(f"[ORIGEN: {source}]\n{doc}\n[FIN_ORIGEN]")
                
            context_str = "\n\n".join(context_pieces)
            intent = IntentRouter.detect_intent(query)
            sys_prompt, human_prompt = self._build_prompts(intent, context_str)
            
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", sys_prompt),
                ("human", human_prompt)
            ])

            chain = prompt_template | self.llm | StrOutputParser()
            respuesta_cruda = chain.invoke({"context": context_str, "query": query})
            
            #  FASE 5: Inyección de la Trazabilidad en la respuesta final
            if fuentes_unicas:
                lista_fuentes = "\n".join([f"* 📄 `{f}`" for f in fuentes_unicas])
                trazabilidad = f"\n\n---\n###  Trazabilidad de Auditoría\n*Documentos base utilizados para este dictamen:*\n{lista_fuentes}"
                return respuesta_cruda + trazabilidad
                
            return respuesta_cruda
            
        except Exception as e:
            logger.error(f"Fallo catastrófico RAG: {str(e)}")
            raise e