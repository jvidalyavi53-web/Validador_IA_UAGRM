import os
import time
import logging
from pathlib import Path

import streamlit as st
import requests

try:
    from streamlit_cookies_controller import CookieController
    COOKIES_AVAILABLE = True
except ImportError as exc:
    COOKIES_AVAILABLE = False
    CookieController = None
    logging.getLogger("UAGRM_Frontend").warning(
        f"streamlit_cookies_controller no disponible ({exc}). "
        "La sesión NO se restaurará tras refrescar el navegador."
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s - FE - %(levelname)s - %(message)s")
logger = logging.getLogger("UAGRM_Frontend")

# ==============================================================================
# 1. CONFIGURACIÓN
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
API_URL = os.getenv("API_URL", "https://validador-ia-uagrm.onrender.com/api/v1").rstrip("/")

REQUEST_TIMEOUT_LOGIN = 15
REQUEST_TIMEOUT_HISTORY = 10
REQUEST_TIMEOUT_ASK = 65
REQUEST_TIMEOUT_UPLOAD = 300
REQUEST_TIMEOUT_CLEAR = 15


# ==============================================================================
# 2. UTILIDADES DE ASSETS
# ==============================================================================
def get_asset(filename: str) -> str:
    path = BASE_DIR / "assets" / filename
    if not path.exists():
        alt_jpg = path.with_suffix(".jpg")
        alt_png = path.with_suffix(".png")
        if path.suffix.lower() == ".jpg" and alt_png.exists():
            return str(alt_png)
        if path.suffix.lower() == ".png" and alt_jpg.exists():
            return str(alt_jpg)
    return str(path)


def render_img(img_path, width, center=False, rounded=False):
    if not os.path.exists(img_path):
        return ""
    try:
        with open(img_path, "rb") as image_file:
            encoded = __import__("base64").b64encode(image_file.read()).decode()
        mime = "image/jpeg" if ".jpg" in img_path.lower() else "image/png"
        radius = "50%" if rounded else "10px"
        img_html = (
            f'<img src="data:{mime};base64,{encoded}" width="{width}" '
            f'style="pointer-events: none; border-radius: {radius}; '
            f'object-fit: cover; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">'
        )
        if center:
            return f'<div style="display: flex; justify-content: center; align-items: center;">{img_html}</div>'
        return img_html
    except Exception:
        return ""


def get_md_image_tag(filename: str, alt_text: str = "icon") -> str:
    import base64
    path = get_asset(filename)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        return f"![{alt_text}](data:{mime};base64,{encoded})"
    except Exception:
        return ""


# ==============================================================================
# 3. LLAMADAS HTTP TIPADAS
# ==============================================================================
def _safe_json(res: requests.Response) -> dict:
    try:
        return res.json()
    except ValueError:
        return {"detail": res.text or f"HTTP {res.status_code}"}


def api_login(username: str, password: str) -> dict:
    try:
        res = requests.post(
            f"{API_URL}/auth/login",
            data={"username": username, "password": password},
            timeout=REQUEST_TIMEOUT_LOGIN,
        )
    except requests.exceptions.Timeout:
        return {"error": "El servidor tardó demasiado en responder (timeout)."}
    except requests.exceptions.ConnectionError:
        return {"error": "No se pudo contactar al backend. Revisa tu conexión."}
    data = _safe_json(res)
    if res.status_code == 200:
        return {"ok": True, "data": data}
    return {"error": data.get("detail", f"HTTP {res.status_code}")}


def api_history(token: str) -> dict:
    try:
        res = requests.get(
            f"{API_URL}/chat/history",
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_HISTORY,
        )
    except requests.exceptions.Timeout:
        return {"error": "Timeout al cargar historial."}
    except requests.exceptions.ConnectionError:
        return {"error": "Sin conexión con el backend."}
    if res.status_code == 200:
        return {"ok": True, "data": _safe_json(res)}
    return {"error": _safe_json(res).get("detail", f"HTTP {res.status_code}")}


def api_ask(token: str, query: str, provider: str) -> dict:
    try:
        res = requests.post(
            f"{API_URL}/chat/ask",
            json={"query": query, "provider": provider},
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_ASK,
        )
    except requests.exceptions.Timeout:
        return {"error": "El modelo tardó demasiado. Reintenta o cambia de modo."}
    except requests.exceptions.ConnectionError:
        return {"error": "Sin conexión con el backend."}
    data = _safe_json(res)
    if res.status_code == 200:
        return {"ok": True, "data": data}
    return {"error": data.get("detail", f"HTTP {res.status_code}")}


def api_upload(token: str, username: str, file_name: str, file_bytes: bytes) -> dict:
    try:
        res = requests.post(
            f"{API_URL}/documents/upload",
            data={"username": username},
            files={"file": (file_name, file_bytes, "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_UPLOAD,
        )
    except requests.exceptions.Timeout:
        return {"error": "Timeout al procesar el PDF. Archivo demasiado grande."}
    except requests.exceptions.ConnectionError:
        return {"error": "Sin conexión con el backend."}
    data = _safe_json(res)
    if res.status_code == 200:
        return {"ok": True, "data": data}
    return {"error": data.get("detail", f"HTTP {res.status_code}")}


def api_clear(token: str, username: str) -> dict:
    try:
        res = requests.post(
            f"{API_URL}/database/clear",
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_CLEAR,
        )
    except requests.exceptions.ConnectionError:
        return {"error": "Sin conexión con el backend."}
    if res.status_code == 200:
        return {"ok": True, "data": _safe_json(res)}
    return {"error": _safe_json(res).get("detail", f"HTTP {res.status_code}")}


# ==============================================================================
# 4. PERSISTENCIA DE SESIÓN CON COOKIES
# ==============================================================================
COOKIE_NAME = "uagrm_session"


def get_cookie_controller():
    if not COOKIES_AVAILABLE:
        raise RuntimeError("streamlit_cookies_controller no instalado")
    return CookieController()


def restore_session_from_cookie() -> bool:
    """Intenta rehidratar la sesión desde la cookie. Devuelve True si lo logró."""
    if not COOKIES_AVAILABLE:
        return False
    try:
        controller = get_cookie_controller()
        token = controller.get(COOKIE_NAME)
    except Exception as exc:
        logger.warning(f"No se pudo leer cookie: {exc}")
        return False

    if not token:
        return False

    # Validar el token con /auth/me
    try:
        res = requests.get(
            f"{API_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_HISTORY,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning(f"Fallo validando sesión restaurada: {exc}")
        return False

    if res.status_code != 200:
        logger.info("Token en cookie inválido o expirado.")
        try:
            controller.remove(COOKIE_NAME)
        except Exception:
            pass
        return False

    data = _safe_json(res)
    st.session_state.access_token = token
    st.session_state.username = data.get("username")
    st.session_state.rol = data.get("rol", "visitante")

    hist = api_history(token)
    if hist.get("ok"):
        st.session_state.mensajes = hist["data"].get("historial", [])
    else:
        st.session_state.mensajes = []
    return True


def save_session_to_cookie(token: str) -> None:
    if not COOKIES_AVAILABLE:
        return
    try:
        controller = get_cookie_controller()
        controller.set(COOKIE_NAME, token)
    except Exception as exc:
        logger.warning(f"No se pudo guardar cookie: {exc}")


def clear_session_cookie() -> None:
    if not COOKIES_AVAILABLE:
        return
    try:
        controller = get_cookie_controller()
        controller.remove(COOKIE_NAME)
    except Exception:
        pass


# ==============================================================================
# 5. CONFIG STREAMLIT + ESTILOS
# ==============================================================================
st.set_page_config(page_title="Validador IA UAGRM", layout="wide")

st.markdown(
    """
<style>
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {display: none !important; pointer-events: none !important;}
    [data-testid="StyledFullScreenButton"] { display: none !important; }
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-thumb { background: var(--text-color); opacity: 0.3; border-radius: 10px; }
    .stApp {
        background-color: var(--background-color);
        background-image: radial-gradient(var(--text-color) 1px, transparent 1px);
        background-size: 25px 25px; opacity: 0.97;
    }
    section[data-testid="stSidebar"] {
        background: var(--secondary-background-color) !important;
        border-right: 1px solid var(--border-color) !important;
        box-shadow: 4px 0 25px rgba(0,0,0,0.5) !important;
        z-index: 9999999 !important;
    }
    [data-testid="stSidebarOverlay"], .stSidebarOverlay { z-index: 9999998 !important; }
    .main .block-container { z-index: 1 !important; }
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, #c8102e 0%, #8a0b1f 100%) !important;
        color: white !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        width: 100% !important;
        border: none !important;
    }
    .auth-card {
        background: var(--secondary-background-color); padding: 40px; border-radius: 15px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1); border: 1px solid var(--border-color);
        max-width: 500px; margin: 0 auto;
    }
    .feature-card {
        background: var(--secondary-background-color); backdrop-filter: blur(10px);
        border-radius: 12px; padding: 30px 25px;
        text-align: center; border: 1px solid var(--border-color);
        box-shadow: 0 4px 15px rgba(0,0,0,0.03); height: 100%;
    }
    .feature-card h4 { color: #c8102e !important; margin-bottom: 12px; font-weight: 800; font-size: 1.1rem; }
    .feature-card p { color: var(--text-color) !important; opacity: 0.8; font-size: 0.9rem; line-height: 1.5; margin: 0; }
    .card-icon-wrapper {
        width: 48px; height: 48px; margin: 0 auto 20px auto; background: var(--background-color);
        border-radius: 10px; display: flex; align-items: center; justify-content: center;
        border: 1px solid var(--border-color);
    }
    [data-testid="stChatMessage"] {
        background: var(--secondary-background-color) !important; border-radius: 12px !important;
        border: 1px solid var(--border-color) !important; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
        padding: 1.5rem !important; margin-bottom: 1rem !important;
        display: flex !important; flex-direction: row !important; gap: 20px !important;
    }
    [data-testid="stChatInput"] {
        border-radius: 12px !important; border: 1px solid var(--border-color) !important;
        background-color: var(--secondary-background-color) !important; padding: 5px 10px !important;
    }
    [data-testid="stChatInput"]:focus-within { border-color: #c8102e !important; }
    hr { border-top: 1px solid var(--border-color); margin-bottom: 2rem; margin-top: 1rem; }
    .stSpinner > div > div {
        border-color: #c8102e transparent transparent transparent !important;
        box-shadow: 0 0 15px #c8102e, 0 0 30px #c8102e;
        animation: spin 1s linear infinite, pulseGlow 1.5s ease-in-out infinite alternate !important;
        border-width: 4px !important;
    }
    @keyframes pulseGlow {
        0% { box-shadow: 0 0 10px #c8102e; }
        100% { box-shadow: 0 0 25px #ff1e46, 0 0 45px #ff1e46; }
    }
    div[data-testid="stSpinner"] > div > p {
        color: #ff1e46 !important;
        font-weight: 800 !important;
        text-shadow: 0 0 8px rgba(200, 16, 46, 0.5);
    }
</style>
""",
    unsafe_allow_html=True,
)

# ==============================================================================
# 6. HEADER
# ==============================================================================
col_izq, col_centro, col_der = st.columns([1, 4, 1])
with col_izq:
    st.markdown(render_img(get_asset("Escudo_FICCT.png"), 110, center=True), unsafe_allow_html=True)
with col_centro:
    st.markdown(
        "<h1 style='text-align: center; font-size: 2.8rem; margin-bottom: 0; font-weight: 800;'>Validador IA - UAGRM</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align: center; font-size: 0.95rem; text-transform: uppercase; letter-spacing: 1px; margin-top: 8px;'>Plataforma API-First Enterprise</p>",
        unsafe_allow_html=True,
    )
with col_der:
    st.markdown(render_img(get_asset("EscudoUAGRM2026.jpg"), 130, center=True), unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# ==============================================================================
# 7. RESTAURAR SESIÓN DESDE COOKIE (si aplica)
# ==============================================================================
if "access_token" not in st.session_state:
    with st.spinner("Restaurando sesión..."):
        if not restore_session_from_cookie():
            st.session_state.access_token = None

# ==============================================================================
# 8. PANTALLA DE LOGIN / REGISTRO
# ==============================================================================
if not st.session_state.get("access_token"):
    st.markdown("<div style='height: 2vh;'></div>", unsafe_allow_html=True)
    st.markdown(
        "<h2 style='text-align: center; font-weight: 800;'>Acceso Institucional</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align: center;'>Ingrese sus credenciales corporativas para continuar</p>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='auth-card'>", unsafe_allow_html=True)

    img_candado = get_md_image_tag("Icono_Candado_IniciarSesion.png", "login")
    img_registro = get_md_image_tag("Icono_Registro_IniciarSesion.png", "register")

    tab1, tab2 = st.tabs(
        [f"{img_candado} Iniciar Sesión", f"{img_registro} Crear Cuenta"]
    )

    with tab1:
        log_user = st.text_input("Usuario", key="log_user")
        log_pass = st.text_input("Contraseña", type="password", key="log_pass")
        if st.button("Conectar al Clúster", type="primary", key="btn_login"):
            with st.spinner("Autenticando..."):
                resultado = api_login(log_user, log_pass)
                if "ok" in resultado:
                    token = resultado["data"]["access_token"]
                    st.session_state.access_token = token
                    st.session_state.username = resultado["data"].get(
                        "username", log_user
                    )
                    st.session_state.rol = resultado["data"].get("rol", "visitante")

                    hist = api_history(token)
                    st.session_state.mensajes = (
                        hist["data"].get("historial", []) if "ok" in hist else []
                    )

                    save_session_to_cookie(token)
                    st.success(
                        f"Acceso concedido (Rol: {st.session_state.rol.upper()})."
                    )
                    time.sleep(0.6)
                    st.rerun()
                else:
                    st.error(resultado.get("error", "Credenciales incorrectas."))

    with tab2:
        reg_user = st.text_input("Nuevo Usuario", key="reg_user")
        reg_pass = st.text_input("Nueva Contraseña", type="password", key="reg_pass")

        reg_rol_display = st.selectbox(
            "Tipo de Cuenta",
            ["Estudiante (Visitante)", "Docente / Autoridad (Administrador)"],
            key="reg_rol",
        )
        reg_rol = "admin" if "Administrador" in reg_rol_display else "visitante"

        reg_secret = ""
        if reg_rol == "admin":
            st.info(
                "ℹ️ Para crear una cuenta de Administrador, necesita el Código de Autorización Institucional."
            )
            reg_secret = st.text_input(
                "Código de Autorización", type="password", key="reg_secret"
            )

        if st.button("Crear Cuenta", type="primary", key="btn_reg"):
            if len(reg_user) < 4:
                st.warning("⚠️ El usuario debe tener al menos 4 caracteres.")
            elif len(reg_pass) < 6:
                st.warning("⚠️ La contraseña debe tener al menos 6 caracteres.")
            else:
                with st.spinner("Registrando..."):
                    try:
                        res = requests.post(
                            f"{API_URL}/auth/register",
                            json={
                                "username": reg_user,
                                "password": reg_pass,
                                "rol": reg_rol,
                                "admin_secret": reg_secret,
                            },
                            timeout=REQUEST_TIMEOUT_LOGIN,
                        )
                    except requests.exceptions.ConnectionError:
                        st.error("No se pudo contactar al backend.")
                    else:
                        data = _safe_json(res)
                        if res.status_code == 200:
                            st.success(
                                f"¡Cuenta de {reg_rol.capitalize()} creada! Inicie sesión."
                            )
                        else:
                            st.error(
                                data.get("detail", "Error al registrar el usuario.")
                            )
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ==============================================================================
# 9. APLICACIÓN PRINCIPAL (autenticado)
# ==============================================================================
if "modo_ia" not in st.session_state:
    st.session_state.modo_ia = "groq"
if "biblioteca" not in st.session_state:
    st.session_state.biblioteca = []
if "mensajes" not in st.session_state:
    st.session_state.mensajes = []


def do_logout():
    for key in ("access_token", "username", "rol", "biblioteca", "mensajes"):
        st.session_state.pop(key, None)
    clear_session_cookie()
    st.rerun()


with st.sidebar:
    st.markdown(
        f"<p style='text-align:center; color:#c8102e; font-weight:bold; font-size:1.1rem;'>Operador: {st.session_state.username} ({st.session_state.rol.upper()})</p>",
        unsafe_allow_html=True,
    )
    if st.button("Cerrar Sesión", use_container_width=True):
        do_logout()

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(
        "<h3 style='text-align: center; font-size: 0.85rem;'>Clúster de Inferencia</h3>",
        unsafe_allow_html=True,
    )

    col_img1, col_btn1 = st.columns([1, 4])
    with col_img1:
        st.markdown(render_img(get_asset("groq-circle.png"), 32), unsafe_allow_html=True)
    with col_btn1:
        if st.button(
            "Nube (Groq) - ACTIVO" if st.session_state.modo_ia == "groq" else "Nube (Groq)",
            use_container_width=True,
        ):
            st.session_state.modo_ia = "groq"
            st.rerun()

    col_img2, col_btn2 = st.columns([1, 4])
    with col_img2:
        st.markdown(render_img(get_asset("ollama_circle.png"), 32), unsafe_allow_html=True)
    with col_btn2:
        if st.button(
            "Local (Ollama) - ACTIVO" if st.session_state.modo_ia == "ollama" else "Local (Ollama)",
            use_container_width=True,
        ):
            st.session_state.modo_ia = "ollama"
            st.rerun()

    if st.session_state.get("rol") == "admin":
        st.markdown("<hr>", unsafe_allow_html=True)
        col_icono, col_titulo = st.columns([1, 4])
        with col_icono:
            st.markdown(
                render_img(get_asset("bandeja_entrada.png"), 32), unsafe_allow_html=True
            )
        with col_titulo:
            st.markdown(
                "<h3 style='margin-top: 2px; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px;'>Pipeline Documental</h3>",
                unsafe_allow_html=True,
            )

        archivo_subido = st.file_uploader(
            "Subir PDF", type=["pdf"], label_visibility="collapsed"
        )

        if archivo_subido and st.button("Procesar Vía API", type="primary"):
            with st.spinner(
                "Leyendo y vectorizando documento (puede tardar en archivos pesados)..."
            ):
                resultado = api_upload(
                    st.session_state.access_token,
                    st.session_state.username,
                    archivo_subido.name,
                    archivo_subido.getvalue(),
                )
                if "ok" in resultado:
                    st.session_state.biblioteca.append(archivo_subido.name)
                    st.success("Documento ingestado en Base Vectorial.")
                    time.sleep(0.8)
                    st.rerun()
                else:
                    st.error(f"Fallo en la API: {resultado.get('error', 'desconocido')}")

        if st.button("[ PURGAR MI MEMORIA RAM ]", use_container_width=True):
            with st.spinner("Purgando..."):
                api_clear(st.session_state.access_token, st.session_state.username)
            st.session_state.biblioteca = []
            st.session_state.mensajes = []
            st.rerun()
    else:
        st.markdown("<hr>", unsafe_allow_html=True)
        st.info(
            "ℹ️ **Modo Visitante:** Puedes consultar a la IA, pero la carga de PDFs está deshabilitada."
        )

# --- CHAT CENTRAL ---
if len(st.session_state.mensajes) == 0:
    st.markdown(
        "<div style='height: 3vh;'></div><h2 style='text-align: center; font-weight: 800;'>Dashboard Seguro (Aislamiento Total)</h2>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        doc_img = render_img(get_asset("Documento_imagen.jpg"), 24)
        st.markdown(
            f"<div class='feature-card'><div class='card-icon-wrapper'>{doc_img}</div><h4>Partición Privada</h4><p>Tus consultas y datos están protegidos en este entorno institucional.</p></div>",
            unsafe_allow_html=True,
        )
    with col2:
        file_img = render_img(get_asset("avatar_archivo.png"), 24)
        st.markdown(
            f"<div class='feature-card'><div class='card-icon-wrapper'>{file_img}</div><h4>Memoria Inteligente</h4><p>El LLM enfoca su atención exclusivamente en la base de conocimiento activa.</p></div>",
            unsafe_allow_html=True,
        )
    st.markdown("<div style='height: 5vh;'></div>", unsafe_allow_html=True)

for msj in st.session_state.mensajes:
    avatar_path = (
        get_asset("avatar_human.png")
        if msj["rol"] == "user"
        else get_asset("asistente_IA.png")
    )
    with st.chat_message(msj["rol"], avatar=avatar_path):
        st.markdown(msj["contenido"], unsafe_allow_html=True)

pregunta = st.chat_input(f"Consulte al motor, {st.session_state.username}...")

if pregunta:
    with st.chat_message("user", avatar=get_asset("avatar_human.png")):
        st.markdown(pregunta)
    st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})

    with st.chat_message("assistant", avatar=get_asset("asistente_IA.png")):
        with st.spinner("Procesando en clúster privado..."):
            resultado = api_ask(
                st.session_state.access_token,
                pregunta,
                st.session_state.modo_ia,
            )
            if "ok" in resultado:
                respuesta = resultado["data"].get("response", "Sin respuesta.")
                st.markdown(respuesta, unsafe_allow_html=True)
                st.session_state.mensajes.append(
                    {"rol": "assistant", "contenido": respuesta}
                )
            else:
                st.error(f"Error: {resultado.get('error', 'fallo desconocido')}")
