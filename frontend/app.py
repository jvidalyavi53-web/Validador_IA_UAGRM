import streamlit as st
import os
import sys
import base64
import uuid
import time
import requests

# ==============================================================================
# 1. CONFIGURACIÓN DE RUTAS Y CONSTANTES
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_URL = "https://validador-ia-uagrm.onrender.com/api/v1"

def get_asset(filename):
    path = os.path.join(BASE_DIR, "assets", filename)
    if not os.path.exists(path):
        alt = path.replace(".jpg", ".png") if ".jpg" in path else path.replace(".png", ".jpg")
        if os.path.exists(alt): return alt
    return path

def render_img(img_path, width, center=False, rounded=False):
    if not os.path.exists(img_path): return ""
    try:
        with open(img_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode()
        mime = "image/jpeg" if "jpg" in img_path.lower() else "image/png"
        radius = "50%" if rounded else "10px"
        img_html = f'<img src="data:{mime};base64,{encoded}" width="{width}" style="pointer-events: none; border-radius: {radius}; object-fit: cover; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">'
        if center:
            return f'<div style="display: flex; justify-content: center; align-items: center;">{img_html}</div>'
        return img_html
    except Exception:
        return ""

def render_icon_inline(img_path, width=20):
    return render_img(img_path, width, rounded=True)

def get_md_image_tag(filename, alt_text="icon"):
    path = get_asset(filename)
    if not os.path.exists(path): return ""
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        return f"![{alt_text}](data:{mime};base64,{encoded})"
    except:
        return ""

st.set_page_config(page_title="Validador IA UAGRM", layout="wide")

# ==============================================================================
# 2. MOTOR DE DISEÑO
# ==============================================================================
st.markdown("""
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
            background: linear-gradient(135deg, #c8102e 0%, #8a0b1f 100%) !important; color: white !important; 
            border-radius: 8px !important; font-weight: 700 !important; width: 100% !important; border: none !important;
        }
        
        .auth-card {
            background: var(--secondary-background-color); padding: 40px; border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1); border: 1px solid var(--border-color);
            max-width: 500px; margin: 0 auto;
        }
        .feature-card {
            background: var(--secondary-background-color); backdrop-filter: blur(10px); border-radius: 12px; padding: 30px 25px;
            text-align: center; border: 1px solid var(--border-color); box-shadow: 0 4px 15px rgba(0,0,0,0.03); height: 100%;
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
            padding: 1.5rem !important; margin-bottom: 1rem !important; display: flex !important; flex-direction: row !important; gap: 20px !important; 
        }
        [data-testid="stChatInput"] { 
            border-radius: 12px !important; border: 1px solid var(--border-color) !important; 
            background-color: var(--secondary-background-color) !important; padding: 5px 10px !important;
        }
        [data-testid="stChatInput"]:focus-within { border-color: #c8102e !important; }
        hr { border-top: 1px solid var(--border-color); margin-bottom: 2rem; margin-top: 1rem; }

        /*  EFECTO SPINNER NEÓN ROJO/CYBERPUNK AÑADIDO AQUÍ */
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
""", unsafe_allow_html=True)

# ==============================================================================
# 3. CABECERA PRINCIPAL
# ==============================================================================
col_izq, col_centro, col_der = st.columns([1, 4, 1])
with col_izq: st.markdown(render_img(get_asset("Escudo_FICCT.png"), 110, center=True), unsafe_allow_html=True)
with col_centro:
    st.markdown("<h1 style='text-align: center; font-size: 2.8rem; margin-bottom: 0; font-weight: 800;'>Validador IA - UAGRM</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 0.95rem; text-transform: uppercase; letter-spacing: 1px; margin-top: 8px;'>Plataforma API-First Enterprise</p>", unsafe_allow_html=True)
with col_der: st.markdown(render_img(get_asset("EscudoUAGRM2026.jpg"), 130, center=True), unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# ==============================================================================
# 4. BARRERA DE SEGURIDAD (LOGIN / REGISTRO)
# ==============================================================================
if "access_token" not in st.session_state:
    st.markdown("<div style='height: 2vh;'></div>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; font-weight: 800;'>Acceso Institucional</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Ingrese sus credenciales corporativas para continuar</p>", unsafe_allow_html=True)
    
    st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
    
    img_candado = get_md_image_tag("Icono_Candado_IniciarSesion.png", "login")
    img_registro = get_md_image_tag("Icono_Registro_IniciarSesion.png", "register")
    
    tab1, tab2 = st.tabs([f"{img_candado} Iniciar Sesión", f"{img_registro} Crear Cuenta"])
    
    with tab1:
        log_user = st.text_input("Usuario")
        log_pass = st.text_input("Contraseña", type="password")
        if st.button("Conectar al Clúster", type="primary", key="btn_login"):
            with st.spinner("Autenticando y restaurando entorno..."):
                try:
                    res = requests.post(f"{API_URL}/auth/login", data={"username": log_user, "password": log_pass})
                    if res.status_code == 200:
                        st.session_state.access_token = res.json().get("access_token")
                        st.session_state.username = log_user
                        st.session_state.rol = res.json().get("rol", "visitante")
                        
                        try:
                            historial_res = requests.get(f"{API_URL}/chat/history/{log_user}")
                            if historial_res.status_code == 200:
                                st.session_state.mensajes = historial_res.json().get("historial", [])
                            else:
                                st.session_state.mensajes = []
                        except:
                            st.session_state.mensajes = []

                        st.success(f"Acceso Concedido (Rol: {st.session_state.rol.upper()}). Inicializando...")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Credenciales denegadas o usuario incorrecto.")
                except requests.exceptions.ConnectionError:
                    st.error("Error de Red: El servidor Backend está apagado.")
                    
    with tab2:
        reg_user = st.text_input("Nuevo Usuario")
        reg_pass = st.text_input("Nueva Contraseña", type="password")
        
        reg_rol_display = st.selectbox("Tipo de Cuenta", ["Estudiante (Visitante)", "Docente / Autoridad (Administrador)"])
        reg_rol = "admin" if "Administrador" in reg_rol_display else "visitante"
        
        reg_secret = ""
        if reg_rol == "admin":
            st.info("ℹ️ Para crear una cuenta de Administrador, necesita el Código de Autorización Institucional.")
            reg_secret = st.text_input("Código de Autorización", type="password")
            
        if st.button("Crear Cuenta", type="primary", key="btn_reg"):
            if len(reg_user) < 4:
                st.warning("⚠️ El usuario debe tener al menos 4 caracteres.")
            elif len(reg_pass) < 6:
                st.warning("⚠️ La contraseña debe tener al menos 6 caracteres.")
            else:
                with st.spinner("Registrando en Base de Datos..."):
                    try:
                        payload = {
                            "username": reg_user, 
                            "password": reg_pass, 
                            "rol": reg_rol,
                            "admin_secret": reg_secret 
                        }
                        res = requests.post(f"{API_URL}/auth/register", json=payload)
                        
                        try:
                            data = res.json()
                        except ValueError:
                            data = {"detail": "Fallo crítico del servidor 500."}

                        if res.status_code == 200:
                            st.success(f"¡Cuenta de {reg_rol.capitalize()} creada exitosamente! Inicie sesión.")
                        else:
                            st.error(data.get("detail", "Error al registrar el usuario."))
                    except requests.exceptions.ConnectionError:
                        st.error("Error de Red: El servidor Backend está apagado.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ==============================================================================
# 5. APLICACIÓN PRINCIPAL
# ==============================================================================
if "modo_ia" not in st.session_state: st.session_state.modo_ia = "groq"
if "biblioteca" not in st.session_state: st.session_state.biblioteca = []
if "mensajes" not in st.session_state: st.session_state.mensajes = []

with st.sidebar:
    st.markdown(f"<p style='text-align:center; color:#c8102e; font-weight:bold; font-size:1.1rem;'>Operador: {st.session_state.username} ({st.session_state.rol.upper()})</p>", unsafe_allow_html=True)
    if st.button("Cerrar Sesión", use_container_width=True):
        del st.session_state["access_token"]
        del st.session_state["username"]
        del st.session_state["rol"]
        st.session_state.biblioteca = []
        st.session_state.mensajes = []
        st.rerun()
        
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; font-size: 0.85rem;'>Clúster de Inferencia</h3>", unsafe_allow_html=True)
    
    col_img1, col_btn1 = st.columns([1, 4])
    with col_img1: st.markdown(render_img(get_asset("groq-circle.png"), 32), unsafe_allow_html=True)
    with col_btn1:
        if st.button("Nube (Groq) - ACTIVO" if st.session_state.modo_ia == "groq" else "Nube (Groq)", use_container_width=True):
            st.session_state.modo_ia = "groq"
            st.rerun()
            
    col_img2, col_btn2 = st.columns([1, 4])
    with col_img2: st.markdown(render_img(get_asset("ollama_circle.png"), 32), unsafe_allow_html=True)
    with col_btn2:
        if st.button("Local (Ollama) - ACTIVO" if st.session_state.modo_ia == "ollama" else "Local (Ollama)", use_container_width=True):
            st.session_state.modo_ia = "ollama"
            st.rerun()

    if st.session_state.get("rol") == "admin":
        st.markdown("<hr>", unsafe_allow_html=True)
        col_icono, col_titulo = st.columns([1, 4])
        with col_icono: st.markdown(render_img(get_asset("bandeja_entrada.png"), 32), unsafe_allow_html=True)
        with col_titulo: st.markdown("<h3 style='margin-top: 2px; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px;'>Pipeline Documental</h3>", unsafe_allow_html=True)
            
        archivo_subido = st.file_uploader("Subir PDF", type=["pdf"], label_visibility="collapsed")

        if archivo_subido and st.button("Procesar Vía API", type="primary"):
            with st.spinner("Leyendo y vectorizando documento (puede tardar en archivos pesados)..."):
                exito = False
                try:
                    datos_form = {"username": st.session_state.username}
                    archivos = {"file": (archivo_subido.name, archivo_subido.getvalue(), "application/pdf")}
                    cabeceras = {"Authorization": f"Bearer {st.session_state.access_token}"}
                    
                    # 🚀 AHORA ESPERA HASTA RECIBIR EL STATUS 200 (SÍNCRONO)
                    res = requests.post(f"{API_URL}/documents/upload", data=datos_form, files=archivos, headers=cabeceras)
                    
                    if res.status_code == 200:
                        st.session_state.biblioteca.append(archivo_subido.name)
                        st.success("Documento blindado e ingestadon en Base Vectorial.")
                        exito = True
                    else: 
                        st.error(f"Fallo en el OCR o Servidor: {res.json().get('detail', res.text)}")
                except requests.exceptions.ConnectionError: 
                    st.error("Error crítico: El servidor Backend ha colapsado o está apagado.")
                
                if exito:
                    time.sleep(1)
                    st.rerun()

        if st.button("[ PURGAR MI MEMORIA RAM ]", use_container_width=True):
            cabeceras = {"Authorization": f"Bearer {st.session_state.access_token}"}
            requests.post(f"{API_URL}/database/clear", json={"username": st.session_state.username}, headers=cabeceras)
            st.session_state.biblioteca = []
            st.session_state.mensajes = []
            st.rerun()
    else:
        st.markdown("<hr>", unsafe_allow_html=True)
        st.info("ℹ️ **Modo Visitante:** Puedes realizar consultas a la IA, pero los privilegios para modificar la Base de Conocimiento (Subir PDFs) están deshabilitados.")

# --- CHAT CENTRAL ---
if len(st.session_state.mensajes) == 0:
    st.markdown("<div style='height: 3vh;'></div><h2 style='text-align: center; font-weight: 800;'>Dashboard Seguro (Aislamiento Total)</h2>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1: 
        doc_img = render_img(get_asset("Documento_imagen.jpg"), 24)
        st.markdown(f"<div class='feature-card'><div class='card-icon-wrapper'>{doc_img}</div><h4>Partición Privada</h4><p>Tus consultas y datos están protegidos en este entorno institucional.</p></div>", unsafe_allow_html=True)
    with col2: 
        file_img = render_img(get_asset("avatar_archivo.png"), 24)
        st.markdown(f"<div class='feature-card'><div class='card-icon-wrapper'>{file_img}</div><h4>Memoria Inteligente</h4><p>El LLM enfoca su atención exclusivamente en la base de conocimiento activa.</p></div>", unsafe_allow_html=True)
    st.markdown("<div style='height: 5vh;'></div>", unsafe_allow_html=True)

for msj in st.session_state.mensajes:
    avatar_path = get_asset("avatar_human.png") if msj["rol"] == "user" else get_asset("asistente_IA.png")
    with st.chat_message(msj["rol"], avatar=avatar_path): 
        st.markdown(msj["contenido"], unsafe_allow_html=True)

pregunta = st.chat_input(f"Consulte al motor, {st.session_state.username}...")

if pregunta:
    with st.chat_message("user", avatar=get_asset("avatar_human.png")): st.markdown(pregunta)
    st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})

    with st.chat_message("assistant", avatar=get_asset("asistente_IA.png")):
        with st.spinner("Procesando en clúster privado..."):
            try:
                payload = {
                    "query": pregunta, 
                    "provider": st.session_state.modo_ia, 
                    "username": st.session_state.username
                }
                res = requests.post(f"{API_URL}/chat/ask", json=payload)
                if res.status_code == 200:
                    respuesta = res.json().get("response", "Error leyendo respuesta.")
                    st.markdown(respuesta, unsafe_allow_html=True)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta})
                else: 
                    st.error("Error del servidor Backend al inferir.")
            except: 
                st.error("Fallo crítico de red.")