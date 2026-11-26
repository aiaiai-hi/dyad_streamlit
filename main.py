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
# 3. УПРАВЛЕНИЕ ПЕСОЧНИЦЕЙ (ВСТРОЕННЫЙ РЕНДЕР)
# ==========================================
WORKSPACE_DIR = "dyad_workspace"
APP_FILE = os.path.join(WORKSPACE_DIR, "app.py")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

def render_generated_app(code_str: str):
    """Выполняет сгенерированный код прямо внутри вкладки Preview."""
    # Убираем st.set_page_config из сгенерированного кода, 
    # так как он уже вызван в основном приложении (иначе будет ошибка Streamlit)
    cleaned_code = re.sub(
        r'st\.set_page_config\s*\(.*?\)', 
        '', 
        code_str, 
        flags=re.DOTALL
    )
    
    # Изолированное пространство имен для выполнения кода
    exec_globals = {
        "__name__": "__main__",
        "st": st,
    }
    exec(cleaned_code, exec_globals)
    
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
    c1, c2, c3, c4 = st.columns([2, 2, 1.5, 1.5])
    vllm_url = c1.text_input("vLLM Base URL", value="http://localhost:8000/v1")
    vllm_model = c2.text_input("Имя модели в vLLM", value="Qwen/Qwen2.5-Coder-32B-Instruct")
    vllm_key = c3.text_input("API Key", value="EMPTY", type="password")
    with c4:
        st.write("")
        st.write("")
        if st.button("🗑️ Новый проект", use_container_width=True):
            stop_preview_server()
            st.session_state["messages"] = []
            st.session_state["code"] = ""
            st.session_state["history"] = []
            st.session_state["runtime_error"] = None
            if os.path.exists(APP_FILE):
                os.remove(APP_FILE)
            st.rerun()

# ==========================================
# 7. ОСНОВНОЙ ЭКРАН: SPLIT-VIEW (ЧАТ | ПРЕВЬЮ)
# ==========================================

left_col, right_col = st.columns([1, 1.35], gap="medium")

# --- ЛЕВАЯ КОЛОНКА: ЧАТ И ЦИКЛ УТОЧНЕНИЯ ---
with left_col:
    chat_container = st.container(height=620, border=False)
    with chat_container:
        if not st.session_state["messages"]:
            st.markdown("""
                Что создадим сегодня?
                Опишите идею внутреннего приложения. Сначала я задам пару уточняющих вопросов (как в Dyad), а затем соберу интерфейс.
            """, unsafe_allow_html=True)
        for msg in st.session_state["messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Кнопка принудительного старта генерации (если модель задала вопросы, но хочется сразу код)
    col_opt1, col_opt2 = st.columns([1, 1])
    with col_opt1:
        auto_clarify = st.toggle("🔍 Уточнять запрос перед кодом", value=True)
    with col_opt2:
        if st.session_state["history"] and len(st.session_state["history"]) > 1:
            if st.button("↩️ Откатить версию кода", use_container_width=True):
                st.session_state["history"].pop()
                st.session_state["code"] = st.session_state["history"][-1]
                with open(APP_FILE, "w", encoding="utf-8") as f:
                    f.write(st.session_state["code"])
                start_preview_server()
                st.rerun()

    user_prompt = st.chat_input("Опишите приложение или попросите изменить дизайн...")

# Обработка отправки сообщения
if user_prompt:
    st.session_state["messages"].append({"role": "user", "content": user_prompt})
    with left_col:
        with st.spinner("Dyad думает..."):
            try:
                need_clarification = False
                # ШАГ 1: Цикл уточнения (если включен и код еще не написан)
                if auto_clarify and not st.session_state["code"]:
                    clarify_reply = call_vllm(
                        st.session_state["messages"],
                        CLARIFIER_SYSTEM_PROMPT,
                        vllm_url, vllm_key, vllm_model, temp=0.3
                    )
                    if "[READY]" not in clarify_reply:
                        need_clarification = True
                        st.session_state["messages"].append({
                            "role": "assistant",
                            "content": f"🤔 Уточним детали перед сборкой:\n\n{clarify_reply}"
                        })

                # ШАГ 2: Генерация или модификация кода
                if not need_clarification:
                    context_messages = list(st.session_state["messages"])
                    if st.session_state["code"]:
                        context_messages.append({
                            "role": "system",
                            "content": f"Текущий код файла app.py:\n```python\n{st.session_state['code']}\n```"
                        })
                    raw_response = call_vllm(
                        context_messages,
                        BUILDER_SYSTEM_PROMPT,
                        vllm_url, vllm_key, vllm_model, temp=0.2
                    )
                    chat_reply, updated_code = parse_dyad_response(raw_response, st.session_state["code"])
                    if updated_code and updated_code != st.session_state["code"]:
                        st.session_state["code"] = updated_code
                        st.session_state["history"].append(updated_code)
                        with open(APP_FILE, "w", encoding="utf-8") as f:
                            f.write(updated_code)
                        start_preview_server()
                    st.session_state["messages"].append({
                        "role": "assistant",
                        "content": chat_reply
                    })
            except Exception as e:
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": f"❌ Ошибка подключения к vLLM: {str(e)}"
                })
    st.rerun()

# --- ПРАВАЯ КОЛОНКА: ВОРКСПЕЙС (PREVIEW | CODE | RUNTIME) ---
with right_col:
    tab_preview, tab_code = st.tabs(["🖥️ Preview (Живое приложение)", "📄 Code (app.py)"])
        with tab_preview:
        # Баннер ошибки Runtime + кнопка Auto-Fix
        if st.session_state.get("runtime_error"):
            st.error("⚠️ Ошибка при запуске сгенерированного приложения:")
            st.code(st.session_state["runtime_error"], language="bash")
            if st.button("✨ Исправить ошибку автоматически (Auto-Fix)", type="primary"):
                fix_prompt = f"При запуске app.py возникла ошибка:\n{st.session_state['runtime_error']}\nИсправь её и верни рабочий код."
                st.session_state["messages"].append({"role": "user", "content": "Исправь ошибку запуска"})
                raw_fix = call_vllm(
                    [{"role": "user", "content": f"Текущий код:\n{st.session_state['code']}\n\n{fix_prompt}"}],
                    BUILDER_SYSTEM_PROMPT,
                    vllm_url, vllm_key, vllm_model, temp=0.1
                )
                _, fixed_code = parse_dyad_response(raw_fix, st.session_state["code"])
                st.session_state["code"] = fixed_code
                st.session_state["history"].append(fixed_code)
                st.session_state["runtime_error"] = None
                with open(APP_FILE, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                st.rerun()

        elif st.session_state["code"]:
            # Оборачиваем в контейнер, чтобы изолировать рендер
            preview_box = st.container(border=True)
            with preview_box:
                try:
                    render_generated_app(st.session_state["code"])
                except Exception as e:
                    import traceback
                    st.session_state["runtime_error"] = traceback.format_exc()
                    st.rerun()
        else:
            st.markdown("""
                <div style="text-align: center; padding: 80px 20px; color: #64748b;">
                    <div style="font-size: 32px; margin-bottom: 10px;">⚡</div>
                    <div style="font-weight: 600; color: #cbd5e1;">Здесь появится превью вашего приложения</div>
                    <div style="font-size: 13px; margin-top: 4px;">Отправьте запрос в чат слева, чтобы начать</div>
                </div>
            """, unsafe_allow_html=True)


    with tab_code:
        if st.session_state["code"]:
            c_dl, c_run = st.columns([1, 1])
            c_dl.download_button(
                "⬇️ Скачать app.py",
                data=st.session_state["code"],
                file_name="app.py",
                mime="text/x-python",
                use_container_width=True
            )
            if c_run.button("🔄 Перезапустить превью", use_container_width=True):
                start_preview_server()
                st.rerun()
            st.code(st.session_state["code"], language="python", line_numbers=True)
        else:
            st.info("Код еще не сгенерирован.")
