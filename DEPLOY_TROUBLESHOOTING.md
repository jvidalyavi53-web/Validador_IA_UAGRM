# Guía de Despliegue y Troubleshooting — Validador IA UAGRM

## Arquitectura

```
┌─────────────────────┐         ┌──────────────────────┐
│  Streamlit Cloud    │  HTTPS  │  Render (FastAPI)    │
│  (frontend/app.py)  │ ──────► │  (backend/main.py)   │
│                     │         │  Uvicorn:10000       │
└─────────────────────┘         └──────────┬───────────┘
                                           │
                                ┌──────────┴──────────┐
                                ▼                     ▼
                       ┌────────────────┐    ┌─────────────────┐
                       │  Neon.tech     │    │  Groq API       │
                       │  PostgreSQL    │    │  (LLM: Llama)   │
                       │  (usuarios,    │    │                 │
                       │   historial)   │    │                 │
                       └────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │  VectorDB LOCAL │
                       │  TF-IDF +       │
                       │  scikit-learn   │
                       │  (sin red)      │
                       └─────────────────┘
```

---

## Variables de entorno

### Backend (Render Dashboard → Environment)

| Variable | Valor | Origen | Obligatoria |
|----------|-------|--------|-------------|
| `GROQ_API_KEY` | `gsk_...` | https://console.groq.com/keys | ✅ |
| `DATABASE_URL` | `postgresql://...neon...` | https://console.neon.tech | ✅ |
| `SECRET_KEY` | (64+ chars) | `python -c "import secrets; print(secrets.token_urlsafe(64))"` | ✅ |
| `ENVIRONMENT` | `production` | — | ✅ |
| `ALLOWED_ORIGINS` | URL de tu app Streamlit | https://validador-ia-uagrm-ficct.streamlit.app | ✅ |
| `GROQ_TIMEOUT` | `30` | default | no |
| `GROQ_MAX_RETRIES` | `2` | default | no |
| `MAX_UPLOAD_MB` | `50` | default | no |
| `MAX_REQUEST_SECONDS` | `50` | default | no |
| `TESSERACT_CMD` | (no setear en Render) | default | no |
| `ADMIN_SECRET` | `FICCT2026` | default | no |

> **Nota:** El sistema ya **NO** usa HuggingFace Inference API. La búsqueda vectorial es **100% local** con TF-IDF + scikit-learn. La variable `HF_API_KEY` ya no es necesaria.

### Frontend (Streamlit Cloud → Settings → Secrets)

```toml
API_URL = "https://validador-ia-uagrm.onrender.com/api/v1"
```

---

## Build Command de Render

**NO es necesario modificar el Build Command.** Render's Python runtime es read-only filesystem y no permite `apt-get install`. En lugar de eso, el proyecto usa **RapidOCR** (pure-Python, ONNX Runtime) que no necesita binarios del sistema.

El Build Command default de Render es:
```bash
pip install -r requirements.txt
```

**Verificación:** en los logs del nuevo deploy debés ver:
```
Successfully installed rapidocr-onnxruntime-1.4.4 ...
```

Y al iniciar el backend:
```
INFO - OCR engine: RapidOCR (ONNX, pure-Python).
INFO - OCR chain (en orden de intento): ['rapidocr']
```

**Si querés Tesseract nativo** (mejor calidad OCR en español), tendrías que migrar a un Dockerfile. No es necesario por ahora.

---

## Verificación end-to-end post-deploy

### 1. Healthcheck (con `HEAD`)

```bash
curl -I https://validador-ia-uagrm.onrender.com/
```

✅ Esperado: `HTTP/1.1 200 OK`  
❌ Si da `405`: revisar que se aplicó el fix de `methods=["GET", "HEAD"]`.

### 2. Healthz con DB

```bash
curl https://validador-ia-uagrm.onrender.com/api/v1/healthz
```

✅ Esperado:
```json
{"status":"ok","db":"ok"}
```

### 3. Login

```bash
curl -X POST https://validador-ia-uagrm.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=TU_USUARIO&password=TU_PASSWORD"
```

✅ Esperado:
```json
{"access_token":"eyJ...","token_type":"bearer","rol":"admin","username":"TU_USUARIO"}
```

### 4. Chat "Hola" (sin OOM)

```bash
TOKEN="PEGA_AQUI_TU_JWT"
curl -X POST https://validador-ia-uagrm.onrender.com/api/v1/chat/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"Hola, ¿quién eres?","provider":"groq"}'
```

✅ Esperado (en <10s):
```json
{
  "response":"Hola, soy el asistente institucional de la UAGRM...",
  "status":"success"
}
```

❌ Si tarda >50s: revisa que `MAX_REQUEST_SECONDS=50` esté aplicado.

### 5. Verificar logs sin OOM

En los logs de Render durante el chat, **NO debe aparecer**:
```
==> Detected service running on port 10000  (entre dos requests)
INFO:     Shutting down
```

Solo puede aparecer el port-detect cada 60s del healthcheck de Render (es normal, no es un restart).

---

## Troubleshooting

### ❌ "ModuleNotFoundError: No module named 'streamlit_cookies_controller'"

Streamlit intentó importar el módulo antes de que terminara el `uv pip install`. **Solución:** refresca la pestaña del frontend. Como el módulo ya está en `requirements.txt`, el siguiente reload lo encuentra.

### ❌ "Tesseract NO disponible"

**Solución actual:** el sistema usa **RapidOCR** (pure-Python) como fallback automático. El warning de Tesseract es esperable y la app sigue funcionando. No requiere acción.

### ❌ Render healthcheck reporta 405 "Method Not Allowed"

El endpoint `/` no acepta `HEAD`. Verificar que el código tenga:
```python
@app.api_route("/", methods=["GET", "HEAD"])
```

### ❌ Chat devuelve 504 "El proveedor de IA no respondió"

Groq está saturado o el token es inválido. Revisa:
1. Logs de Render por `Timeout en chat para {usuario} tras 50s`
2. Que `GROQ_API_KEY` esté bien configurada en Environment
3. Probar cambiar a `provider: "ollama"` si tenés Ollama local

### ❌ "Cannot connect to backend" en Streamlit

1. Verificar que el backend esté vivo: `curl -I https://validador-ia-uagrm.onrender.com/`
2. Verificar `API_URL` en Streamlit Cloud Secrets
3. Verificar `ALLOWED_ORIGINS` en Render (debe coincidir con la URL de Streamlit)

### ❌ "El nombre de usuario ya está ocupado"

El usuario ya existe en Neon. Probar con otro nombre o entrar con `psql`:
```sql
DELETE FROM usuarios WHERE username = 'TU_USUARIO';
```

### ❌ "Credenciales incorrectas" tras refresh de Streamlit

La cookie de sesión fue limpiada o el token expiró (24h). Solo volver a loguear.

### ❌ `Failed to resolve 'api-inference.huggingface.co'`

**Bug histórico — ya corregido.** La versión actual usa TF-IDF local (scikit-learn) en vez de la API de HuggingFace. Si el error reaparece:
1. Verificar que `vector_db.py` NO importe `chromadb` ni `embedding_functions`
2. Confirmar que `requirements.txt` NO tenga `chromadb`
3. Redesplegar

### ❌ PDFs escaneados no se procesan

Si después de instalar Tesseract un PDF escaneado sigue dando error, verificar:
1. Tamaño del PDF (límite `MAX_UPLOAD_MB`)
2. Que el PDF no esté encriptado
3. Logs: `INFO - Procesando PDF: X páginas`

---

## Optimización para producción

### Embeddings remotos (HF API) - ✅ ya activo

Con `EMBEDDING_PROVIDER=huggingface_api` no se carga ningún modelo local. Las embeddings se calculan en la nube de HuggingFace, ahorrando ~400MB de RAM en Render Free Tier.

### Límite de cuota HF

La Inference API free tier tiene ~1000 req/h. Si se excede, los PDFs subidos fallarán con error de HuggingFace. **Mitigación futura:** cachear embeddings por hash de chunk.

### Cache de conversaciones

Las conversaciones se persisten en Neon (PostgreSQL). Sin embargo, la VectorDB está en RAM (EphemeralClient) y se pierde en cada restart. **Para producción real:** considerar migrar a `PersistentClient` con un volume de Render (no disponible en plan Free).

---

## Rollback

Si algo sale mal y necesitás volver a una versión anterior:

```bash
git log --oneline -5          # ver commits
git revert HEAD               # revertir último commit
git push origin main          # Render redeploya automáticamente
```

O bien en Render Dashboard: **Manual Deploy** → seleccionar commit anterior.

---

## Monitoreo

- **Logs de Render:** https://dashboard.render.com/web/SERVICIO/logs
- **Logs de Streamlit:** https://share.streamlit.io/ → tu app → menú ⋯ → Logs
- **Estado de Neon:** https://console.neon.tech → tu proyecto → Monitoring
- **Cuota de HF:** https://huggingface.co/settings/billing

---

## Próximos pasos opcionales

1. **Dominio personalizado** (configurar CNAME en Render)
2. **Migrar a Render Starter ($7/mes)** para más RAM y eliminar cold starts
3. **Reemplazar ChromaDB por pgvector** (extensión de PostgreSQL) para persistencia
4. **Implementar refresh tokens** para sesiones más largas
5. **Agregar rate limiting** con `slowapi` para evitar abuso
6. **Tests automatizados** con `pytest` y CI/CD en GitHub Actions
