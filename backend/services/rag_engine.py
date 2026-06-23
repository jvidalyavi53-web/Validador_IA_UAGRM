import os
import re
import logging
from typing import Tuple
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger("UAGRM_RAGEngine")

load_dotenv()

GROQ_TIMEOUT = float(os.getenv("GROQ_TIMEOUT", "30"))
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "2"))
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "2048"))


class IntentRouter:
    """Arquitectura de Enrutamiento Semántico para Validaciones."""

    @staticmethod
    def detect_intent(query: str) -> str:
        query_cleaned = query.lower().strip()
        audit_patterns = [
            r"\bvalidar\b", r"\bresolución\b", r"\bresolucion\b",
            r"\baprobar\b", r"\bevaluar\b", r"\bauditar\b", r"\bdictaminar\b",
        ]
        if any(re.search(pattern, query_cleaned) for pattern in audit_patterns):
            return "JUEZ_NORMATIVO"
        return "ASESOR_ACADEMICO"


class RAGEngine:
    """Motor Core de Recuperación Aumentada."""

    def __init__(self, vdb_instance, provider: str = "groq"):
        self.vdb = vdb_instance
        self.provider = provider
        self.llm = self._initialize_llm()

    def _initialize_llm(self):
        if self.provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GROQ_API_KEY no está definida en las variables de entorno."
                )
            return ChatGroq(
                temperature=0.01,
                model_name=GROQ_MODEL,
                api_key=api_key,
                max_tokens=GROQ_MAX_TOKENS,
                timeout=GROQ_TIMEOUT,
                max_retries=GROQ_MAX_RETRIES,
            )
        return ChatOllama(
            model="llama3",
            temperature=0.1,
            num_predict=1024,
            repeat_penalty=1.25,
        )

    def set_provider(self, provider: str) -> None:
        """Cambia de proveedor de manera segura (una sola vez por motor)."""
        if provider == self.provider:
            return
        self.provider = provider
        self.llm = self._initialize_llm()

    def _build_prompts(self, intent: str, context: str) -> Tuple[str, str]:
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
                "3. CRÍTICO: Si la pregunta requiere información de diferentes documentos, DEBES cruzar los datos y unificarlos en tu respuesta.\n"
                "4. NO inventes información. Responde estrictamente con los datos proporcionados en el corpus.\n\n"
                "<CORPUS_DOCUMENTAL>\n{context}\n</CORPUS_DOCUMENTAL>"
            )
            human_reinforcement = (
                "CONSULTA DEL USUARIO:\n{query}\n\n"
                "INSTRUCCIÓN FINAL: Responde con claridad, cruza la información si es necesario y mantén una estructura profesional."
            )
        return system_prompt, human_reinforcement

    def _ask_conversational(self, query: str) -> str:
        """Saludo / charla casual: NO carga ChromaDB ni embeddings."""
        system_prompt = (
            "ACTÚAS EXCLUSIVAMENTE COMO: Asistente Institucional de la UAGRM.\n"
            "MISIÓN: Saludar y orientar al usuario sobre la plataforma Validador IA UAGRM.\n\n"
            "REGLAS:\n"
            "1. Saluda cordialmente y preséntate como el asistente institucional.\n"
            "2. Indica que el usuario puede subir documentos normativos (PDF) desde la barra lateral "
            "si su rol es Administrador.\n"
            "3. Si te piden validar/auditar algo, recuerda que la base de conocimiento está vacía hasta "
            "que se carguen PDFs.\n"
            "4. Sé breve, claro y profesional.\n"
        )
        human_prompt = (
            f"CONSULTA DEL USUARIO:\n{query}\n\n"
            "INSTRUCCIÓN FINAL: Responde con un saludo institucional breve."
        )
        prompt_template = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("human", human_prompt)]
        )
        chain = prompt_template | self.llm | StrOutputParser()
        return chain.invoke({})

    def ask(self, query: str) -> str:
        try:
            if not self.vdb.is_ready():
                logger.info("VectorDB vacía: respondiendo en modo conversacional.")
                return self._ask_conversational(query)

            # FIX CRÍTICO: Aumentamos a 20 resultados. 
            # Como los chunks ahora son pequeños, traer 20 permite que la IA vea múltiples documentos a la vez.
            search_results = self.vdb.search(query, n_results=20)
            if (
                not search_results
                or not search_results.get("documents")
                or not search_results["documents"][0]
            ):
                return "**OBSERVADO**\n\nLa base de conocimiento está vacía o no se encontraron coincidencias."

            context_pieces = []
            fuentes_unicas = set()

            for doc, meta in zip(
                search_results["documents"][0],
                search_results.get("metadatas", [[]])[0],
            ):
                source = meta.get("source", "Documento_Desconocido")
                fuentes_unicas.add(source)
                context_pieces.append(f"[ORIGEN: {source}]\n{doc}\n[FIN_ORIGEN]")

            context_str = "\n\n".join(context_pieces)
            intent = IntentRouter.detect_intent(query)
            sys_prompt, human_prompt = self._build_prompts(intent, context_str)

            prompt_template = ChatPromptTemplate.from_messages(
                [("system", sys_prompt), ("human", human_prompt)]
            )
            chain = prompt_template | self.llm | StrOutputParser()
            respuesta_cruda = chain.invoke({"context": context_str, "query": query})

            if fuentes_unicas:
                lista_fuentes = "\n".join([f"* 📄 `{f}`" for f in fuentes_unicas])
                trazabilidad = (
                    "\n\n---\n### Trazabilidad de Auditoría\n"
                    "*Documentos base utilizados para este dictamen:*\n"
                    f"{lista_fuentes}"
                )
                return respuesta_cruda + trazabilidad

            return respuesta_cruda

        except Exception as e:
            logger.error(f"Fallo RAG: {str(e)}")
            raise RuntimeError(f"Fallo en el motor RAG: {str(e)}") from e