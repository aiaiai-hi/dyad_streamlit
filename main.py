import streamlit as st
import subprocess
import socket
import time
import re
import os
import signal
from openai import OpenAI

# ==========================================
# 1. НАСТРОЙКА СТРАНИЦЫ И СТИЛЬ DYAD (CSS)
# ==========================================
st.set_page_config(
    page_title="Dyad Internal • AI App Builder",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Фирменный минималистичный стиль в духе Dyad / Linear
st.markdown("""
<style>
    /* Убираем стандартные отступы и хедер Streamlit */
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1.2rem !important;
        padding-right: 1.2rem !important;
        max-width: 100% !important;
    }
    
    /* Общий фон и шрифты */
    .stApp {
        background-color: #0b0f19;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    }

    /* Верхняя панель навигации (Topbar как в Dyad) */
    .dyad-topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 8px 16px;
        margin-bottom: 12px;
    }
    .dyad-logo {
        font-weight: 700;
        font-size: 16px;
        color: #f8fafc;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .dyad-badge {
        background: rgba(99, 102, 241, 0.15);
        color: #818cf8;
        border: 1px solid rgba(99, 102, 241, 0.3);
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 600;
    }

    /* Контейнеры чата */
    [data-testid="stChatMessage"] {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
    
    /* Кнопки */
    .stButton > button {
        background-color: #1f2937;
        color: #f3f4f6;
        border: 1px solid #374151;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        background-color: #374151;
        border-color: #6366f1;
        color: #ffffff;
    }
    
    /* Кнопка Primary */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
        border: none;
        color: white;
    }

    /* Вкладки (Preview / Code) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #111827;
        padding: 4px;
        border-radius: 8px;
        border: 1px solid #1f2937;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: #9ca3af;
        padding: 4px 14px;
        font-size: 13px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f2937 !important;
        color: #ffffff !important;
    }

    /* Рамка превью */
    iframe {
        border: 1px solid #1f2937 !important;
        border-radius: 10px !important;
        background: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. СИСТЕМНЫЕ ПРОМПТЫ (ЛОГИКА DYAD)
# ==========================================

CLARIFIER_SYSTEM_PROMPT = """Ты — системный аналитик в AI-среде разработки Dyad.
Твоя задача перед генерацией кода — убедиться, что запрос пользователя достаточно конкретен для создания красивого внутреннего приложения на Streamlit.

ПРАВИЛА:
1. Если запрос слишком общий (например, "сделай дашборд" или "сделай CRM") и это первое сообщение: задай 2-3 коротких, конкретных вопроса (какие метрики/поля нужны, какие действия, нужна ли фильтрация). Предложи краткие варианты ответа.
2. Если пользователь уже ответил на уточняющие вопросы ИЛИ исходный запрос уже содержит достаточно деталей для MVP ИЛИ в проекте уже есть код и пользователь просит правку — НЕ задавай вопросов! Ответь строго одним словом: [READY]
"""

BUILDER_SYSTEM_PROMPT = """Ты — Dyad AI, экспертный full-stack разработчик внутренних приложений на Python + Streamlit.
Ты создаешь приложения с дизайном уровня современных React / Shadcn UI интерфейсов, используя ТОЛЬКО стандартный `streamlit`, `pandas`, `numpy`, `plotly` и чистый HTML/CSS через `st.markdown(..., unsafe_allow_html=True)`.

СТРОГИЕ ПРАВИЛА СРЕДЫ:
- ЗАПРЕЩЕНО использовать внешние UI-библиотеки (`streamlit-shadcn-ui`, `streamlit-extras`), Google Fonts или внешние CDN (закрытый контур без интернета).
- Приложение должно работать в одном файле `app.py` с реалистичными тестовыми (mock) данными.
- Обязательно внедряй кастомный CSS в начале `app.py`: скрывай стандартный `header` и `footer`, делай современные карточки (`border-radius: 12px`, `border: 1px solid #e2e8f0`, мягкие тени), аккуратные бейджи и системную типографику.

ФОРМАТ ВЫВОДА (КАК В DYAD):
Сначала кратко (1-2 предложения) объясни пользователю, что ты сделал.
Затем выдай код строго внутри XML-тега `<dyad-write path="app.py">...</dyad-write>`.
Если ты вносишь небольшую правку в существующий код, ты можешь либо перезаписать файл через `<dyad-write path="app.py">`, либо использовать блок замены:
<dyad-search-replace path="app.py">
<<<<<<< SEARCH
старый фрагмент кода
=======
новый фрагмент кода
>>>>>>> REPLACE
</dyad-search-replace>
"""

# ==========================================
# 3. УПРАВЛЕНИЕ ПЕСОЧНИЦЕЙ (SUBPROCESS + PORT)
# ==========================================
WORKSPACE_DIR = "dyad_workspace"
APP_FILE = os.path.join(WORKSPACE_DIR, "app.py")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def stop_preview_server():
    proc = st.session_state.get("preview_proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    st.session_state["preview_proc"] = None

def start_preview_server():
    stop_preview_server()
    if not os.path.exists(APP_FILE):
        return
    
    port = get_free_port()
    st.session_state["preview_port"] = port
    
    # Запускаем дочерний Streamlit без открытия браузера
    cmd = [
        "streamlit", "run", APP_FILE,
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "light"
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    st.session_state["preview_proc"] = proc
    time.sleep(1.8)  # Даем серверу время подняться
    
    # Проверяем, не упал ли процесс сразу при старте
    if proc.poll() is not None:
        _, stderr = proc.communicate()
        st.session_state["runtime_error"] = stderr
    else:
        st.session_state["runtime_error"] = None

# ==========================================
# 4. ПАРСЕР ОТВЕТОВ DYAD И РАБОТА С vLLM
# ==========================================
def parse_dyad_response(text: str, current_code: str) -> tuple[str, str]:
    """Извлекает объяснение и применяет теги <dyad-write> или <dyad-search-replace>."""
    new_code = current_code
    
    # 1. Проверяем полную перезапись файла
    write_match = re.search(r'<dyad-write[^>]*>(.*?)</dyad-write>', text, re.DOTALL)
    if write_match:
        new_code = write_match.group(1).strip()
        # Убираем случайные markdown-обертки ```python внутри тега
        new_code = re.sub(r'^```python\s*|```$', '', new_code, flags=re.MULTILINE).strip()
    
    # 2. Проверяем точечные патчи SEARCH/REPLACE
    patch_matches = re.findall(
        r'<dyad-search-replace[^>]*>.*?<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE.*?</dyad-search-replace>',
        text,
        re.DOTALL
    )
    for search_block, replace_block in patch_matches:
        if search_block in new_code:
            new_code = new_code.replace(search_block, replace_block)

    # Очищаем текст для чата от громоздких XML-тегов
    clean_chat_text = re.sub(r'<dyad-(write|search-replace).*?</dyad-\1>', '', text, flags=re.DOTALL).strip()
    if not clean_chat_text:
        clean_chat_text = "✅ Код обновлен и отправлен в превью."
        
    return clean_chat_text, new_code

def call_vllm(messages, system_prompt, base_url, api_key, model_name, temp=0.2):
    client = OpenAI(base_url=base_url, api_key=api_key)
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    response = client.chat.completions.create(
        model=model_name,
        messages=full_messages,
        temperature=temp,
        max_tokens=4096
    )
    return response.choices[0].message.content

# ==========================================
# 5. ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ (SESSION STATE)
# ==========================================
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "code" not in st.session_state:
    st.session_state["code"] = ""
if "history" not in st.session_state:
    st.session_state["history"] = []  # Версии кода для отката как в Dyad
if "runtime_error" not in st.session_state:
    st.session_state["runtime_error"] = None
if "skip_clarify" not in st.session_state:
    st.session_state["skip_clarify"] = False

# ==========================================
# 6. ВЕРХНЯЯ ПАНЕЛЬ (DYAD TOPBAR) & НАСТРОЙКИ vLLM
# ==========================================
st.markdown("""
<div class="dyad-topbar">
    <div class="dyad-logo">
        ⚡ Dyad Studio <span class="dyad-badge">Streamlit Engine • vLLM</span>
    </div>
    <div style="font-size: 12px; color: #9ca3af;">
        Внутренний контур • Python Runtime
    </div>
</div>
""", unsafe_allow_html=True)

with st.expander("⚙️ Подключение к vLLM и управление проектом", expanded=False):
import streamlit as st
import subprocess
import socket
import time
import re
import os
import signal
from openai import OpenAI

# ==========================================
# 1. НАСТРОЙКА СТРАНИЦЫ И СТИЛЬ DYAD (CSS)
# ==========================================
st.set_page_config(
    page_title="Dyad Internal • AI App Builder",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Фирменный минималистичный стиль в духе Dyad / Linear
st.markdown("""
<style>
    /* Убираем стандартные отступы и хедер Streamlit */
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1.2rem !important;
        padding-right: 1.2rem !important;
        max-width: 100% !important;
    }
    
    /* Общий фон и шрифты */
    .stApp {
        background-color: #0b0f19;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    }

    /* Верхняя панель навигации (Topbar как в Dyad) */
    .dyad-topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 8px 16px;
        margin-bottom: 12px;
    }
    .dyad-logo {
        font-weight: 700;
        font-size: 16px;
        color: #f8fafc;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .dyad-badge {
        background: rgba(99, 102, 241, 0.15);
        color: #818cf8;
        border: 1px solid rgba(99, 102, 241, 0.3);
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 600;
    }

    /* Контейнеры чата */
    [data-testid="stChatMessage"] {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
    
    /* Кнопки */
    .stButton > button {
        background-color: #1f2937;
        color: #f3f4f6;
        border: 1px solid #374151;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        background-color: #374151;
        border-color: #6366f1;
        color: #ffffff;
    }
    
    /* Кнопка Primary */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
        border: none;
        color: white;
    }

    /* Вкладки (Preview / Code) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #111827;
        padding: 4px;
        border-radius: 8px;
        border: 1px solid #1f2937;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: #9ca3af;
        padding: 4px 14px;
        font-size: 13px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f2937 !important;
        color: #ffffff !important;
    }

    /* Рамка превью */
    iframe {
        border: 1px solid #1f2937 !important;
        border-radius: 10px !important;
        background: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. СИСТЕМНЫЕ ПРОМПТЫ (ЛОГИКА DYAD)
# ==========================================

CLARIFIER_SYSTEM_PROMPT = """Ты — системный аналитик в AI-среде разработки Dyad.
Твоя задача перед генерацией кода — убедиться, что запрос пользователя достаточно конкретен для создания красивого внутреннего приложения на Streamlit.

ПРАВИЛА:
1. Если запрос слишком общий (например, "сделай дашборд" или "сделай CRM") и это первое сообщение: задай 2-3 коротких, конкретных вопроса (какие метрики/поля нужны, какие действия, нужна ли фильтрация). Предложи краткие варианты ответа.
2. Если пользователь уже ответил на уточняющие вопросы ИЛИ исходный запрос уже содержит достаточно деталей для MVP ИЛИ в проекте уже есть код и пользователь просит правку — НЕ задавай вопросов! Ответь строго одним словом: [READY]
"""

BUILDER_SYSTEM_PROMPT = """Ты — Dyad AI, экспертный full-stack разработчик внутренних приложений на Python + Streamlit.
Ты создаешь приложения с дизайном уровня современных React / Shadcn UI интерфейсов, используя ТОЛЬКО стандартный `streamlit`, `pandas`, `numpy`, `plotly` и чистый HTML/CSS через `st.markdown(..., unsafe_allow_html=True)`.

СТРОГИЕ ПРАВИЛА СРЕДЫ:
- ЗАПРЕЩЕНО использовать внешние UI-библиотеки (`streamlit-shadcn-ui`, `streamlit-extras`), Google Fonts или внешние CDN (закрытый контур без интернета).
- Приложение должно работать в одном файле `app.py` с реалистичными тестовыми (mock) данными.
- Обязательно внедряй кастомный CSS в начале `app.py`: скрывай стандартный `header` и `footer`, делай современные карточки (`border-radius: 12px`, `border: 1px solid #e2e8f0`, мягкие тени), аккуратные бейджи и системную типографику.

ФОРМАТ ВЫВОДА (КАК В DYAD):
Сначала кратко (1-2 предложения) объясни пользователю, что ты сделал.
Затем выдай код строго внутри XML-тега `<dyad-write path="app.py">...</dyad-write>`.
Если ты вносишь небольшую правку в существующий код, ты можешь либо перезаписать файл через `<dyad-write path="app.py">`, либо использовать блок замены:
<dyad-search-replace path="app.py">
<<<<<<< SEARCH
старый фрагмент кода
=======
новый фрагмент кода
>>>>>>> REPLACE
</dyad-search-replace>
"""

# ==========================================
# 3. УПРАВЛЕНИЕ ПЕСОЧНИЦЕЙ (SUBPROCESS + PORT)
# ==========================================
WORKSPACE_DIR = "dyad_workspace"
APP_FILE = os.path.join(WORKSPACE_DIR, "app.py")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def stop_preview_server():
    proc = st.session_state.get("preview_proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    st.session_state["preview_proc"] = None

def start_preview_server():
    stop_preview_server()
    if not os.path.exists(APP_FILE):
        return
    
    port = get_free_port()
    st.session_state["preview_port"] = port
    
    # Запускаем дочерний Streamlit без открытия браузера
    cmd = [
        "streamlit", "run", APP_FILE,
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "light"
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    st.session_state["preview_proc"] = proc
    time.sleep(1.8)  # Даем серверу время подняться
    
    # Проверяем, не упал ли процесс сразу при старте
    if proc.poll() is not None:
        _, stderr = proc.communicate()
        st.session_state["runtime_error"] = stderr
    else:
        st.session_state["runtime_error"] = None

# ==========================================
# 4. ПАРСЕР ОТВЕТОВ DYAD И РАБОТА С vLLM
# ==========================================
def parse_dyad_response(text: str, current_code: str) -> tuple[str, str]:
    """Извлекает объяснение и применяет теги <dyad-write> или <dyad-search-replace>."""
    new_code = current_code
    
    # 1. Проверяем полную перезапись файла
    write_match = re.search(r'<dyad-write[^>]*>(.*?)</dyad-write>', text, re.DOTALL)
    if write_match:
        new_code = write_match.group(1).strip()
        # Убираем случайные markdown-обертки ```python внутри тега
        new_code = re.sub(r'^```python\s*|```$', '', new_code, flags=re.MULTILINE).strip()
    
    # 2. Проверяем точечные патчи SEARCH/REPLACE
    patch_matches = re.findall(
        r'<dyad-search-replace[^>]*>.*?<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE.*?</dyad-search-replace>',
        text,
        re.DOTALL
    )
    for search_block, replace_block in patch_matches:
        if search_block in new_code:
            new_code = new_code.replace(search_block, replace_block)

    # Очищаем текст для чата от громоздких XML-тегов
    clean_chat_text = re.sub(r'<dyad-(write|search-replace).*?</dyad-\1>', '', text, flags=re.DOTALL).strip()
    if not clean_chat_text:
        clean_chat_text = "✅ Код обновлен и отправлен в превью."
        
    return clean_chat_text, new_code

def call_vllm(messages, system_prompt, base_url, api_key, model_name, temp=0.2):
    client = OpenAI(base_url=base_url, api_key=api_key)
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    response = client.chat.completions.create(
        model=model_name,
        messages=full_messages,
        temperature=temp,
        max_tokens=4096
    )
    return response.choices[0].message.content

# ==========================================
# 5. ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ (SESSION STATE)
# ==========================================
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "code" not in st.session_state:
    st.session_state["code"] = ""
if "history" not in st.session_state:
    st.session_state["history"] = []  # Версии кода для отката как в Dyad
if "runtime_error" not in st.session_state:
    st.session_state["runtime_error"] = None
if "skip_clarify" not in st.session_state:
    st.session_state["skip_clarify"] = False

# ==========================================
# 6. ВЕРХНЯЯ ПАНЕЛЬ (DYAD TOPBAR) & НАСТРОЙКИ vLLM
# ==========================================
st.markdown("""
<div class="dyad-topbar">
    <div class="dyad-logo">
        ⚡ Dyad Studio <span class="dyad-badge">Streamlit Engine • vLLM</span>
    </div>
    <div style="font-size: 12px; color: #9ca3af;">
        Внутренний контур • Python Runtime
    </div>
</div>
""", unsafe_allow_html=True)

with st.expander("⚙️ Подключение к vLLM и управление проектом", expanded=False):
