import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.rag_engine import RAGEngine

# Prueba local (Ollama) si estás en tu PC con la RTX 3050
# engine = RAGEngine(provider="ollama") 

# Prueba en la nube (Groq) si estás en una laptop liviana
engine = RAGEngine(provider="groq")

pregunta = "¿A nombre de quién está el formulario y qué periodo indica?"

try:
    print(f"\nPreguntando: {pregunta}...")
    respuesta = engine.ask(pregunta)
    print("\n--- RESPUESTA DE LA IA ---")
    print(respuesta)
    print("--------------------------\n")
except Exception as e:
    print(f"Error: {e}")