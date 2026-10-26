import os
import sys
import re
import json
import uuid
import shutil
import platform
import subprocess
import threading
import urllib.request
import ctypes
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
from google import genai
from google.genai import types
from openai import OpenAI

# ================= СТИЛЬ И ТЕМА =================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

THEME = {
    "bg_root": "#0a0b0e",
    "bg_sidebar": "#101217",
    "bg_card": "#161922",
    "bg_input": "#1a1d27",
    "border": "#262b3a",
    "border_focus": "#6366f1",
    "accent": "#6366f1",
    "accent_hover": "#4f46e5",
    "accent_glow": "#818cf8",
    "danger": "#ef4444",
    "danger_hover": "#dc2626",
    "text_main": "#f3f4f6",
    "text_muted": "#858d9d",
    "bubble_user": "#282d3f",
    "bubble_agent": "#151821",
    "code_bg": "#0c0d12",
    "code_inline_bg": "#1e2230",
    "code_inline_fg": "#a5b4fc",
    "table_bg": "#12141c",
    "badge_bg": "#1e2230"
}

# ================= ПУТИ И ДАННЫЕ =================
def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = get_base_dir()
DATA_FILE = os.path.join(SCRIPT_DIR, "pycodex_data.json")
PROVIDERS_FILE = os.path.join(SCRIPT_DIR, "providers.json")

try:
    os.chdir(SCRIPT_DIR)
except Exception:
    pass

DEFAULT_PROVIDERS = {
    "Google AI Studio": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"]
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["nvidia/nemotron-3-ultra-550b-a55b:free", "poolside/laguna-s-2.1:free", "cohere/north-mini-code:free"]
    }
}

if not os.path.exists(PROVIDERS_FILE):
    with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_PROVIDERS, f, ensure_ascii=False, indent=2)

def load_providers() -> dict:
    try:
        with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and data:
                return data
    except Exception:
        pass
    return DEFAULT_PROVIDERS

CORE_SYSTEM_PROMPT = (
    "Ты PyCodex — автономный ИИ-разработчик нового поколения с доступом к системе.\n"
    "У тебя есть 12 системных инструментов:\n"
    "1. run_shell_command, 2. write_file, 3. read_file, 4. replace_in_file,\n"
    "5. list_directory, 6. search_in_files, 7. file_exists, 8. delete_path,\n"
    "9. copy_move_path, 10. get_system_info, 11. download_url, 12. fetch_web_page.\n\n"
    "ОФОРМЛЕНИЕ:\n"
    "- Используй Markdown: жирный (**текст**), инлайн-код (`файл.py`), списки.\n"
    "- Блоки кода оформляй через ```язык ... ```."
)

DEFAULT_CUSTOM_PROMPT = "Отвечай понятно, структурированно и без лишней 'воды' на русском языке."

# ================= 12 ИНСТРУМЕНТОВ =================
def run_shell_command(command: str) -> str:
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
        return f"[Код: {res.returncode}]\n{res.stdout}\n{res.stderr}".strip()
    except Exception as e:
        return f"Ошибка терминала: {str(e)}"

def write_file(filepath: str, content: str) -> str:
    try:
        d = os.path.dirname(filepath)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Файл '{filepath}' успешно сохранен ({len(content)} симв.)."
    except Exception as e:
        return f"Ошибка записи: {str(e)}"

def read_file(filepath: str, offset_lines: int = 0, limit_lines: int = 200) -> str:
    try:
        if not os.path.exists(filepath):
            return f"Файл '{filepath}' не найден."
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        selected = lines[offset_lines : offset_lines + limit_lines]
        return "".join(selected)
    except Exception as e:
        return f"Ошибка чтения: {str(e)}"

def replace_in_file(filepath: str, target_block: str, replacement_block: str) -> str:
    try:
        if not os.path.exists(filepath):
            return f"Файл '{filepath}' не найден."
        with open(filepath, "r", encoding="utf-8") as f:
            c = f.read()
        if target_block not in c:
            return "Фрагмент для замены не обнаружен в файле."
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(c.replace(target_block, replacement_block, 1))
        return f"Файл '{filepath}' обновлен."
    except Exception as e:
        return f"Ошибка: {str(e)}"

def list_directory(dirpath: str = ".") -> str:
    try:
        if not os.path.exists(dirpath):
            return f"Папка '{dirpath}' не существует."
        items = os.listdir(dirpath)
        out = [f"📁 {i}/" if os.path.isdir(os.path.join(dirpath, i)) else f"📄 {i}" for i in sorted(items)]
        return "\n".join(out) if out else "(папка пуста)"
    except Exception as e:
        return f"Ошибка: {str(e)}"

def search_in_files(query: str, root_dir: str = ".", max_results: int = 15) -> str:
    try:
        matches = []
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", "__pycache__", "node_modules")]
            for file in files:
                p = os.path.join(root, file)
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f, 1):
                            if query.lower() in line.lower():
                                matches.append(f"{p}:{idx}: {line.strip()[:140]}")
                                if len(matches) >= max_results:
                                    return "\n".join(matches) + "\n...[лимит совпадений]"
                except Exception:
                    pass
        return "\n".join(matches) if matches else "Совпадений не найдено."
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"

def file_exists(path: str) -> str:
    if os.path.exists(path):
        t = "Каталог" if os.path.isdir(path) else "Файл"
        return f"Существует ({t}): {os.path.abspath(path)}"
    return f"Не существует: {path}"

def delete_path(path: str) -> str:
    try:
        if not os.path.exists(path):
            return "Путь не найден."
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return f"'{path}' удален."
    except Exception as e:
        return f"Ошибка удаления: {str(e)}"

def copy_move_path(src: str, dst: str, operation: str = "copy") -> str:
    try:
        if operation == "move":
            shutil.move(src, dst)
        else:
            (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
        return f"Успешно: {operation} из {src} в {dst}"
    except Exception as e:
        return f"Ошибка перемещения: {str(e)}"

def get_system_info() -> str:
    return f"ОС: {platform.system()} {platform.release()} | Python {sys.version.split()[0]} | Рабочая папка: {os.getcwd()}"

def download_url(url: str, save_path: str) -> str:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r, open(save_path, 'wb') as f:
            shutil.copyfileobj(r, f)
        return f"Файл сохранен в {save_path}"
    except Exception as e:
        return f"Ошибка скачивания: {e}"

def fetch_web_page(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode('utf-8', errors='ignore')[:3500]
    except Exception as e:
        return f"Ошибка: {e}"

ALL_TOOLS = [
    run_shell_command, write_file, read_file, replace_in_file,
    list_directory, search_in_files, file_exists, delete_path,
    copy_move_path, get_system_info, download_url, fetch_web_page
]
TOOLS_DICT = {fn.__name__: fn for fn in ALL_TOOLS}

OPENAI_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": t.__name__,
            "description": t.__name__,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in t.__code__.co_varnames[:t.__code__.co_argcount]}
            }
        }
    } for t in ALL_TOOLS
]

# ================= ХРАНИЛИЩЕ =================
def load_data():
    providers = load_providers()
    default_prov = list(providers.keys())[0] if providers else "Google AI Studio"
    default_model = providers[default_prov]["models"][0] if providers and providers[default_prov]["models"] else "gemini-3.8-flash"

    if not os.path.exists(DATA_FILE):
        return {
            "settings": {"api_key": "", "provider": default_prov, "model": default_model, "custom_prompt": DEFAULT_CUSTOM_PROMPT, "mode": "Default"},
            "chats": []
        }
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "settings": {"api_key": "", "provider": default_prov, "model": default_model, "custom_prompt": DEFAULT_CUSTOM_PROMPT, "mode": "Default"},
            "chats": []
        }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================= ТОЧНЫЙ MARKDOWN LABEL =================
class MarkdownLabel(tk.Text):
    def __init__(self, parent, markdown_text, **kwargs):
        super().__init__(
            parent,
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            bg=THEME["bg_root"],
            cursor="arrow",
            font=("Segoe UI", 12),
            **kwargs
        )
        self._setup_tags()
        self.set_markdown(markdown_text)

    def _setup_tags(self):
        self.tag_configure("normal", font=("Segoe UI", 12), foreground=THEME["text_main"])
        self.tag_configure("bold", font=("Segoe UI", 12, "bold"), foreground="#ffffff")
        self.tag_configure("italic", font=("Segoe UI", 12, "italic"), foreground="#d1d5db")
        self.tag_configure("strike", font=("Segoe UI", 12, "overstrike"), foreground="#9ca3af")
        self.tag_configure("inline_code", font=("Consolas", 11), background=THEME["code_inline_bg"], foreground=THEME["code_inline_fg"])
        self.tag_configure("h1", font=("Segoe UI", 15, "bold"), foreground="#ffffff")
        self.tag_configure("h2", font=("Segoe UI", 13, "bold"), foreground="#ffffff")
        self.tag_configure("h3", font=("Segoe UI", 12, "bold"), foreground=THEME["accent_glow"])
        self.tag_configure("bullet", font=("Segoe UI", 12, "bold"), foreground=THEME["accent_glow"])
        self.tag_configure("table_mono", font=("Consolas", 11), background=THEME["table_bg"], foreground="#d1d5db")

    def set_markdown(self, raw_text):
        self.configure(state="normal")
        self.delete("1.0", "end")

        lines = [line.rstrip() for line in raw_text.strip().split("\n")]
        clean_lines = []
        for l in lines:
            if not l and clean_lines and not clean_lines[-1]:
                continue
            clean_lines.append(l)

        for idx, line in enumerate(clean_lines):
            stripped = line.strip()

            if re.match(r'^-{3,}$', stripped):
                self.insert("end", "―" * 45 + "\n", "table_mono")
                continue

            if stripped.startswith("|") and stripped.endswith("|"):
                self.insert("end", line + "\n", "table_mono")
                continue

            if stripped.startswith("### "):
                self._insert_formatted(line[4:], "h3")
            elif stripped.startswith("## "):
                self._insert_formatted(line[3:], "h2")
            elif stripped.startswith("# "):
                self._insert_formatted(line[2:], "h1")
            elif re.match(r'^\s*[-*•]\s+', line):
                indent_match = re.match(r'^(\s*)[-*•]\s+(.*)', line)
                if indent_match:
                    indent, content = indent_match.groups()
                    self.insert("end", f"{indent}• ", "bullet")
                    self._insert_formatted(content, "normal")
            else:
                self._insert_formatted(line, "normal")

            if idx < len(clean_lines) - 1:
                self.insert("end", "\n")

        self.configure(state="disabled")
        total_rows = sum(max(1, (len(l) // 72) + 1) for l in clean_lines)
        self.configure(height=max(1, total_rows))

    def _insert_formatted(self, text, base_tag):
        pattern = re.compile(r'(`[^`]+`|\*\*[^*]+\*\*|~~[^~]+~~|\*[^*]+\*)')
        parts = pattern.split(text)
        for part in parts:
            if not part:
                continue
            if part.startswith("`") and part.endswith("`"):
                self.insert("end", f" {part[1:-1]} ", "inline_code")
            elif part.startswith("**") and part.endswith("**"):
                self.insert("end", part[2:-2], "bold")
            elif part.startswith("~~") and part.endswith("~~"):
                self.insert("end", part[2:-2], "strike")
            elif part.startswith("*") and part.endswith("*"):
                self.insert("end", part[1:-1], "italic")
            else:
                self.insert("end", part, base_tag)

# ================= ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ =================
class PyCodex(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PyCodex")
        self.geometry("1200x820")
        self.minsize(980, 650)
        self.configure(fg_color=THEME["bg_root"])

        self.data = load_data()
        self.current_chat_id = None
        self.attached_file_path = None
        self.is_generating = False
        self.stop_requested = False

        self.spinner_frames = ["◜", "◠", "◝", "◞", "◡", "◟"]
        self.spinner_idx = 0
        self.current_status_text = "Генерация ответа"
        self.thinking_frame = None
        self.thinking_label = None

        self._set_icon()
        self._build_layout()
        self._load_chats_to_sidebar()

    def _get_app_icon(self, size=(24, 24)):
        for ext in ["png", "ico", "jpg"]:
            path = os.path.join(SCRIPT_DIR, f"PyCodex.{ext}")
            if os.path.exists(path):
                try:
                    pil_img = Image.open(path)
                    return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
                except Exception:
                    pass
        return None

    def _set_icon(self):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PyCodex.App.2.0")
        except Exception:
            pass

        for ext in ["ico", "png"]:
            p = os.path.join(SCRIPT_DIR, f"PyCodex.{ext}")
            if os.path.exists(p):
                try:
                    self.iconbitmap(p)
                    break
                except Exception:
                    pass

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=0, minsize=260)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # САЙДБАР
        self.sidebar = ctk.CTkFrame(self, fg_color=THEME["bg_sidebar"], corner_radius=0, border_width=1, border_color=THEME["border"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(2, weight=1)

        self.logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.logo_frame.grid(row=0, column=0, padx=20, pady=(20, 15), sticky="ew")

        sidebar_icon = self._get_app_icon(size=(26, 26))
        if sidebar_icon:
            self.lbl_logo_icon = ctk.CTkLabel(self.logo_frame, text="", image=sidebar_icon)
            self.lbl_logo_icon.pack(side="left", padx=(0, 10))

        self.lbl_logo = ctk.CTkLabel(
            self.logo_frame, text="PyCodex", font=("Segoe UI", 20, "bold"),
            text_color=THEME["accent_glow"]
        )
        self.lbl_logo.pack(side="left")

        self.btn_new = ctk.CTkButton(
            self.sidebar, text="+ Новый диалог", font=("Segoe UI", 13, "bold"),
            fg_color=THEME["accent"], hover_color=THEME["accent_hover"], text_color="#ffffff",
            corner_radius=10, height=40, command=self.create_new_chat
        )
        self.btn_new.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")

        self.chat_list_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent")
        self.chat_list_scroll.grid(row=2, column=0, padx=8, pady=0, sticky="nsew")

        self.sidebar_bottom = ctk.CTkFrame(self.sidebar, fg_color=THEME["bg_card"], corner_radius=12, border_width=1, border_color=THEME["border"])
        self.sidebar_bottom.grid(row=3, column=0, padx=12, pady=14, sticky="ew")

        self.btn_settings_quick = ctk.CTkButton(
            self.sidebar_bottom, text="⚙ Настройки системы", font=("Segoe UI", 12),
            fg_color="transparent", hover_color=THEME["bg_input"], text_color=THEME["text_muted"],
            anchor="w", height=36, command=self.open_settings
        )
        self.btn_settings_quick.pack(fill="x", padx=4, pady=4)

        # ОСНОВНАЯ ЧАСТЬ
        self.main_area = ctk.CTkFrame(self, fg_color=THEME["bg_root"], corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.grid_rowconfigure(1, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        # Топбар
        self.topbar = ctk.CTkFrame(self.main_area, fg_color=THEME["bg_sidebar"], height=52, corner_radius=0, border_width=1, border_color=THEME["border"])
        self.topbar.grid(row=0, column=0, sticky="ew")

        self.lbl_chat_title = ctk.CTkLabel(
            self.topbar, text="", font=("Segoe UI", 13, "bold"), text_color=THEME["text_main"]
        )
        self.lbl_chat_title.pack(side="left", padx=25)

        self.badge_model = ctk.CTkButton(
            self.topbar, text="", font=("Segoe UI", 11),
            fg_color=THEME["badge_bg"], hover_color=THEME["bubble_user"], text_color=THEME["text_muted"],
            corner_radius=20, height=28, command=self.open_settings
        )
        self.badge_model.pack(side="right", padx=20)
        self._update_badge()

        # Сообщения
        self.messages_scroll = ctk.CTkScrollableFrame(self.main_area, fg_color="transparent")
        self.messages_scroll.grid(row=1, column=0, sticky="nsew", padx=30, pady=(15, 5))
        self.messages_scroll.grid_columnconfigure(0, weight=1)

        # Док ввода
        self.input_dock = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.input_dock.grid(row=2, column=0, sticky="ew", padx=35, pady=(0, 20))
        self.input_dock.grid_columnconfigure(0, weight=1)

        self.file_preview = ctk.CTkFrame(self.input_dock, fg_color=THEME["badge_bg"], corner_radius=8)
        self.lbl_file_attached = ctk.CTkLabel(self.file_preview, text="", font=("Segoe UI", 11), text_color=THEME["accent_glow"])
        self.lbl_file_attached.pack(side="left", padx=10, pady=4)
        self.btn_remove_file = ctk.CTkButton(self.file_preview, text="✕", width=20, height=20, fg_color="transparent", hover_color="#333", command=self._detach_file)
        self.btn_remove_file.pack(side="right", padx=6)

        self.input_pill = ctk.CTkFrame(
            self.input_dock, fg_color=THEME["bg_card"],
            corner_radius=22, border_width=1, border_color=THEME["border"]
        )
        self.input_pill.pack(fill="x", pady=(4, 0))
        self.input_pill.grid_columnconfigure(1, weight=1)

        self.btn_attach = ctk.CTkButton(
            self.input_pill, text="📎", width=36, height=36,
            font=("Segoe UI", 16), fg_color="transparent", hover_color=THEME["bg_input"],
            text_color=THEME["text_muted"], corner_radius=18, command=self.attach_file
        )
        self.btn_attach.grid(row=0, column=0, padx=(10, 5), pady=8, sticky="s")

        self.txt_input = ctk.CTkTextbox(
            self.input_pill, height=44, font=("Segoe UI", 13),
            fg_color="transparent", text_color=THEME["text_main"], wrap="word"
        )
        self.txt_input.grid(row=0, column=1, padx=5, pady=8, sticky="ew")
        self.txt_input.bind("<Control-Return>", self._handle_ctrl_enter)
        self.txt_input.bind("<Control-KP_Enter>", self._handle_ctrl_enter)

        self.btn_send = ctk.CTkButton(
            self.input_pill, text="↑", width=36, height=36,
            font=("Segoe UI", 18, "bold"), fg_color=THEME["accent"], hover_color=THEME["accent_hover"],
            corner_radius=18, text_color="#ffffff", command=self.send_message
        )
        self.btn_send.grid(row=0, column=2, padx=(5, 10), pady=8, sticky="s")

    def _handle_ctrl_enter(self, event):
        self.send_message()
        return "break"

    def _update_badge(self):
        m = self.data["settings"].get("model", "gemini-3.8-flash")
        mode = self.data["settings"].get("mode", "Default")
        prefix = "⚡ Turbo" if mode == "Turbo" else "🛡️ Safe"
        self.badge_model.configure(text=f"{prefix} • {m}")

    def _load_chats_to_sidebar(self):
        for widget in self.chat_list_scroll.winfo_children():
            widget.destroy()

        if not self.data["chats"]:
            self.create_new_chat()
            return

        for chat in reversed(self.data["chats"]):
            is_active = (chat["id"] == self.current_chat_id)
            btn = ctk.CTkButton(
                self.chat_list_scroll, text=f"  {chat['title']}", anchor="w",
                font=("Segoe UI", 12, "bold" if is_active else "normal"),
                fg_color=THEME["bg_card"] if is_active else "transparent",
                hover_color=THEME["bg_input"],
                text_color=THEME["text_main"] if is_active else THEME["text_muted"],
                border_width=1 if is_active else 0,
                border_color=THEME["border"],
                corner_radius=9, height=38,
                command=lambda cid=chat["id"]: self.select_chat(cid)
            )
            btn.bind("<Button-3>", lambda e, cid=chat["id"]: self._show_chat_context_menu(e, cid))
            btn.pack(fill="x", pady=2)

        if not self.current_chat_id and self.data["chats"]:
            self.select_chat(self.data["chats"][0]["id"])

    def _show_chat_context_menu(self, event, chat_id):
        menu = tk.Menu(self, tearoff=0, bg=THEME["bg_card"], fg="#ffffff", activebackground=THEME["accent"], bd=0)
        menu.add_command(label="✎ Переименовать", command=lambda: self.rename_chat(chat_id))
        menu.add_command(label="🗑 Удалить диалог", command=lambda: self.delete_chat(chat_id))
        menu.tk_popup(event.x_root, event.y_root)

    def create_new_chat(self):
        cid = str(uuid.uuid4())
        num = len(self.data["chats"]) + 1
        new_c = {"id": cid, "title": f"Диалог {num}", "messages": []}
        self.data["chats"].append(new_c)
        save_data(self.data)
        self.select_chat(cid)

    def select_chat(self, chat_id):
        self.current_chat_id = chat_id
        chat = next((c for c in self.data["chats"] if c["id"] == chat_id), None)
        if chat:
            self.lbl_chat_title.configure(text=chat["title"])
        self._load_chats_to_sidebar()
        self._render_current_messages()

    def rename_chat(self, chat_id):
        chat = next((c for c in self.data["chats"] if c["id"] == chat_id), None)
        if not chat:
            return
        dialog = ctk.CTkInputDialog(text="Новое название беседы:", title="Переименование")
        new_title = dialog.get_input()
        if new_title and new_title.strip():
            chat["title"] = new_title.strip()
            save_data(self.data)
            self.lbl_chat_title.configure(text=chat["title"])
            self._load_chats_to_sidebar()

    def delete_chat(self, chat_id):
        if len(self.data["chats"]) <= 1:
            messagebox.showinfo("PyCodex", "Нельзя удалить единственный диалог.")
            return
        self.data["chats"] = [c for c in self.data["chats"] if c["id"] != chat_id]
        save_data(self.data)
        self.select_chat(self.data["chats"][-1]["id"])

    # ================= РЕНДЕР СООБЩЕНИЙ =================
    def _render_current_messages(self):
        for widget in self.messages_scroll.winfo_children():
            widget.destroy()

        chat = next((c for c in self.data["chats"] if c["id"] == self.current_chat_id), None)
        if not chat or not chat["messages"]:
            self._render_empty_state()
            return

        for msg in chat["messages"]:
            self._add_message_card(msg["role"], msg["content"])

    def _render_empty_state(self):
        wrapper = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        wrapper.pack(expand=True, pady=60)

        center_icon = self._get_app_icon(size=(56, 56))
        if center_icon:
            ctk.CTkLabel(wrapper, text="", image=center_icon).pack(pady=(0, 6))
        else:
            ctk.CTkLabel(wrapper, text=">_", font=("Consolas", 36, "bold"), text_color=THEME["accent_glow"]).pack(pady=(0, 6))

        ctk.CTkLabel(wrapper, text="PyCodex", font=("Segoe UI", 22, "bold"), text_color=THEME["text_main"]).pack(pady=(0, 4))
        ctk.CTkLabel(wrapper, text="Автономный ИИ-ассистент с прямым доступом к системе", font=("Segoe UI", 12), text_color=THEME["text_muted"]).pack()

        cards_f = ctk.CTkFrame(wrapper, fg_color="transparent")
        cards_f.pack(pady=30)

        prompts = [
            ("📁 Файлы проекта", "Покажи структуру директорий проекта"),
            ("⚙ Окружение", "Выведи информацию об ОС и Python"),
            ("⚡ Автоматизация", "Помоги написать полезный скрипт для проекта")
        ]

        for title, p_text in prompts:
            b = ctk.CTkButton(
                cards_f, text=f"{title}\n{p_text}", font=("Segoe UI", 11),
                fg_color=THEME["bg_card"], hover_color=THEME["bg_input"], text_color=THEME["text_muted"],
                border_width=1, border_color=THEME["border"], corner_radius=12,
                width=180, height=65, command=lambda pt=p_text: self._inject_prompt(pt)
            )
            b.pack(side="left", padx=8)

    def _inject_prompt(self, text):
        self.txt_input.delete("1.0", "end")
        self.txt_input.insert("1.0", text)
        self.send_message()

    def _add_message_card(self, role, text):
        box = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
        box.pack(fill="x", pady=4, padx=15)

        if role == "user":
            bubble = ctk.CTkFrame(box, fg_color=THEME["bubble_user"], corner_radius=16, border_width=1, border_color=THEME["border"])
            bubble.pack(side="right", anchor="e")
            lbl = ctk.CTkLabel(bubble, text=text, font=("Segoe UI", 13), text_color="#ffffff", wraplength=620, justify="left")
            lbl.pack(padx=16, pady=10)

        elif role == "agent":
            header = ctk.CTkFrame(box, fg_color="transparent")
            header.pack(fill="x", pady=(0, 2))

            msg_icon = self._get_app_icon(size=(16, 16))
            if msg_icon:
                ctk.CTkLabel(header, text="", image=msg_icon).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(header, text="PyCodex", font=("Segoe UI", 11, "bold"), text_color=THEME["accent_glow"]).pack(side="left")
            self._render_formatted_content(box, text)

        elif role == "system":
            sys_badge = ctk.CTkFrame(box, fg_color=THEME["badge_bg"], corner_radius=8, border_width=1, border_color=THEME["border"])
            sys_badge.pack(anchor="center", pady=2)
            ctk.CTkLabel(sys_badge, text=text, font=("Consolas", 11), text_color=THEME["text_muted"]).pack(padx=12, pady=4)

        self._safe_scroll_down()

    def _render_formatted_content(self, parent_frame, text):
        parts = re.split(r'(```[\s\S]*?```)', text)
        for part in parts:
            clean_part = part.strip()
            if not clean_part:
                continue

            if part.startswith("```") and part.endswith("```"):
                code_content = part[3:-3]
                first_nl = code_content.find("\n")
                lang = "Код"
                if first_nl != -1 and first_nl < 15:
                    lang = code_content[:first_nl].strip() or "Код"
                    code_body = code_content[first_nl+1:]
                else:
                    code_body = code_content

                card = ctk.CTkFrame(parent_frame, fg_color=THEME["code_bg"], corner_radius=10, border_width=1, border_color=THEME["border"])
                card.pack(fill="x", pady=(2, 6))

                bar = ctk.CTkFrame(card, fg_color="#12141c", height=28, corner_radius=0)
                bar.pack(fill="x")
                ctk.CTkLabel(bar, text=f"  {lang}", font=("Consolas", 11, "bold"), text_color=THEME["text_muted"]).pack(side="left")

                btn_copy = ctk.CTkButton(
                    bar, text="Копировать", width=75, height=22, font=("Segoe UI", 10),
                    fg_color=THEME["badge_bg"], hover_color=THEME["accent"], text_color=THEME["text_main"],
                    command=lambda cb=code_body: self._copy_to_clipboard(cb)
                )
                btn_copy.pack(side="right", padx=6, pady=3)

                code_lbl = ctk.CTkLabel(card, text=code_body.strip(), font=("Consolas", 12), text_color="#d1d5db", justify="left", wraplength=700)
                code_lbl.pack(anchor="w", padx=14, pady=8)
            else:
                md_view = MarkdownLabel(parent_frame, clean_part)
                md_view.pack(anchor="w", fill="x", pady=(0, 2))

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text.strip())

    # ================= СТРИМИНГ БУБЛОВ =================
    def _create_stream_bubble(self):
        evt = threading.Event()
        holder = [None, None]

        def create():
            self._ui_stop_thinking()
            box = ctk.CTkFrame(self.messages_scroll, fg_color="transparent")
            box.pack(fill="x", pady=4, padx=15)

            header = ctk.CTkFrame(box, fg_color="transparent")
            header.pack(fill="x", pady=(0, 2))

            stream_icon = self._get_app_icon(size=(16, 16))
            if stream_icon:
                ctk.CTkLabel(header, text="", image=stream_icon).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(header, text="PyCodex", font=("Segoe UI", 11, "bold"), text_color=THEME["accent_glow"]).pack(side="left")

            bubble = ctk.CTkLabel(box, text="▌", font=("Segoe UI", 13), text_color=THEME["text_main"], justify="left", wraplength=700)
            bubble.pack(anchor="w", padx=4)
            self._safe_scroll_down()
            holder[0], holder[1] = box, bubble
            evt.set()

        self.after(0, create)
        evt.wait()
        return holder[0], holder[1]

    def _update_stream_bubble(self, bubble, text, is_done=False):
        def update():
            try:
                if bubble.winfo_exists():
                    bubble.configure(text=text if is_done else (text + " ▌"))
                    self._safe_scroll_down()
            except Exception:
                pass
        self.after(0, update)

    # ================= ФАЙЛЫ И ОТПРАВКА =================
    def attach_file(self):
        f = filedialog.askopenfilename()
        if f:
            self.attached_file_path = f
            self.file_preview.pack(fill="x", pady=(0, 4))
            self.lbl_file_attached.configure(text=f"📎 {os.path.basename(f)}")

    def _detach_file(self):
        self.attached_file_path = None
        self.file_preview.pack_forget()

    def send_message(self):
        if self.is_generating:
            self.stop_requested = True
            return

        api_key = self.data["settings"].get("api_key")
        if not api_key:
            messagebox.showwarning("Ключ API", "Укажите ваш API Ключ в Настройках!")
            self.open_settings()
            return

        text = self.txt_input.get("1.0", "end").strip()
        if not text and not self.attached_file_path:
            return

        if self.attached_file_path:
            try:
                with open(self.attached_file_path, "r", encoding="utf-8") as f:
                    file_body = f.read()
                text += f"\n\n[Прикрепленный файл {os.path.basename(self.attached_file_path)}]:\n```\n{file_body}\n```"
            except Exception as e:
                text += f"\n\n[Ошибка чтения: {e}]"
            self._detach_file()

        self.txt_input.delete("1.0", "end")
        self._append_message("user", text)

        self.is_generating = True
        self.stop_requested = False
        self.btn_send.configure(text="■", fg_color=THEME["danger"], hover_color=THEME["danger_hover"])

        self._start_thinking_animation("Анализ задачи")
        threading.Thread(target=self._run_agent, daemon=True).start()

    def _append_message(self, role, content):
        def add():
            chat = next(c for c in self.data["chats"] if c["id"] == self.current_chat_id)
            chat["messages"].append({"role": role, "content": content})
            save_data(self.data)
            self._add_message_card(role, content)
        if threading.current_thread() is threading.main_thread():
            add()
        else:
            self.after(0, add)

    # ================= ЛОГИКА АГЕНТА =================
    def _run_agent(self):
        try:
            providers = load_providers()
            prov_name = self.data["settings"].get("provider", "Google AI Studio")
            prov_config = providers.get(prov_name, {})
            base_url = prov_config.get("base_url", "").strip()
            api_key = self.data["settings"]["api_key"]
            model_name = self.data["settings"].get("model", "gemini-3.8-flash")

            chat_obj = next(c for c in self.data["chats"] if c["id"] == self.current_chat_id)
            combined_prompt = f"{CORE_SYSTEM_PROMPT}\n\n[Пользовательские установки]:\n{self.data['settings'].get('custom_prompt', '')}"

            if base_url and prov_name != "Google AI Studio":
                # OpenRouter и прочие OpenAI-совместимые провайдеры
                client = OpenAI(base_url=base_url, api_key=api_key)
                messages = [{"role": "system", "content": combined_prompt}]
                for m in chat_obj["messages"]:
                    r = "assistant" if m["role"] == "agent" else m["role"]
                    if r in ("user", "assistant"):
                        messages.append({"role": r, "content": m["content"]})

                while not self.stop_requested:
                    self.current_status_text = "Печатает"
                    stream = client.chat.completions.create(
                        model=model_name, messages=messages, tools=OPENAI_TOOLS_SCHEMA, tool_choice="auto", stream=True
                    )
                    acc_text, tool_calls_dict = "", {}
                    box_w, stream_lbl = None, None

                    for chunk in stream:
                        if self.stop_requested:
                            break
                        delta = chunk.choices[0].delta if chunk.choices else None
                        if not delta:
                            continue

                        if delta.content:
                            acc_text += delta.content
                            if not stream_lbl:
                                box_w, stream_lbl = self._create_stream_bubble()
                            self._update_stream_bubble(stream_lbl, acc_text)

                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                idx = tc.index
                                if idx not in tool_calls_dict:
                                    tool_calls_dict[idx] = {"id": tc.id or "", "name": tc.function.name or "", "arguments": tc.function.arguments or ""}
                                else:
                                    if tc.id: tool_calls_dict[idx]["id"] += tc.id
                                    if tc.function and tc.function.name: tool_calls_dict[idx]["name"] += tc.function.name
                                    if tc.function and tc.function.arguments: tool_calls_dict[idx]["arguments"] += tc.function.arguments

                    if stream_lbl:
                        self._update_stream_bubble(stream_lbl, acc_text, is_done=True)

                    if tool_calls_dict:
                        formatted_calls = []
                        for idx, td in sorted(tool_calls_dict.items()):
                            formatted_calls.append({"id": td["id"] or f"call_{uuid.uuid4().hex[:6]}", "type": "function", "function": {"name": td["name"], "arguments": td["arguments"]}})

                        messages.append({"role": "assistant", "content": acc_text or None, "tool_calls": formatted_calls})
                        for call in formatted_calls:
                            fn = call["function"]["name"]
                            try:
                                args = json.loads(call["function"]["arguments"])
                            except Exception:
                                args = {}

                            self.current_status_text = f"⚙ {fn}"
                            if self._check_tool_allowed(fn, args):
                                self._append_message("system", f"⚙ {fn} -> {args}")
                                res = TOOLS_DICT[fn](**args) if fn in TOOLS_DICT else "Инструмент не найден"
                            else:
                                res = "Отменено пользователем."
                                self._append_message("system", f"⛔ Отмена: {fn}")

                            messages.append({"role": "tool", "tool_call_id": call["id"], "content": str(res)})
                            self._start_thinking_animation("Анализ")
                    else:
                        if acc_text:
                            chat_obj["messages"].append({"role": "agent", "content": acc_text})
                            save_data(self.data)
                        break
            else:
                # Нативный клиент Google AI Studio (с исправлениями для мульти-инструментов)
                client = genai.Client(api_key=api_key)
                config = types.GenerateContentConfig(system_instruction=combined_prompt, tools=ALL_TOOLS)
                history = [
                    types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part.from_text(text=m["content"])])
                    for m in chat_obj["messages"]
                ]
                session = client.chats.create(model=model_name, config=config, history=history[:-1])
                curr_inp = history[-1].parts[0].text

                while not self.stop_requested:
                    self.current_status_text = "Печатает ответ"
                    stream = session.send_message_stream(curr_inp)
                    acc_text, pending_calls = "", []
                    box_w, stream_lbl = None, None

                    for chunk in stream:
                        if self.stop_requested:
                            break
                        if chunk.function_calls:
                            pending_calls.extend(chunk.function_calls)
                        if chunk.text:
                            acc_text += chunk.text
                            if not stream_lbl:
                                box_w, stream_lbl = self._create_stream_bubble()
                            self._update_stream_bubble(stream_lbl, acc_text)

                    if stream_lbl:
                        self._update_stream_bubble(stream_lbl, acc_text, is_done=True)

                    if pending_calls:
                        response_parts = []
                        for call in pending_calls:
                            fn = call.name
                            args = dict(call.args)
                            self.current_status_text = f"⚙ {fn}"
                            if self._check_tool_allowed(fn, args):
                                self._append_message("system", f"⚙ {fn} -> {args}")
                                res = TOOLS_DICT[fn](**args) if fn in TOOLS_DICT else "Инструмент не найден"
                            else:
                                res = "Отменено пользователем."
                                self._append_message("system", f"⛔ Отклонено: {fn}")

                            response_parts.append(
                                types.Part.from_function_response(
                                    name=fn, 
                                    response={"result": str(res)}
                                )
                            )
                        curr_inp = response_parts
                        self._start_thinking_animation("Синтез данных")
                    else:
                        if acc_text:
                            chat_obj["messages"].append({"role": "agent", "content": acc_text})
                            save_data(self.data)
                        break

        except Exception as e:
            self._append_message("system", f"Ошибка: {str(e)}")
        finally:
            self._stop_thinking_animation()
            def finish_ui():
                self.is_generating = False
                self.btn_send.configure(text="↑", fg_color=THEME["accent"], hover_color=THEME["accent_hover"])
                self._render_current_messages()
            self.after(0, finish_ui)

    def _check_tool_allowed(self, fn_name, fn_args):
        if self.data["settings"].get("mode", "Default") == "Turbo":
            return True
        evt = threading.Event()
        allowed = [False]
        def ask():
            allowed[0] = messagebox.askyesno("Подтверждение действия", f"ИИ хочет вызвать:\n{fn_name}\nАргументы:\n{json.dumps(fn_args, indent=2, ensure_ascii=False)}", parent=self)
            evt.set()
        self.after(0, ask)
        evt.wait()
        return allowed[0]

    # ================= АНИМАЦИЯ ДУМАЙТЕЛЬНЫХ БУБЛОВ =================
    def _start_thinking_animation(self, status="Думает"):
        self.after(0, lambda: self._ui_start_thinking(status))

    def _ui_start_thinking(self, status):
        self.current_status_text = status
        if not self.thinking_frame:
            self.thinking_frame = ctk.CTkFrame(self.messages_scroll, fg_color=THEME["badge_bg"], corner_radius=20, border_width=1, border_color=THEME["border"])
            self.thinking_frame.pack(side="top", anchor="w", padx=15, pady=4)

            self.thinking_label = ctk.CTkLabel(
                self.thinking_frame, text="", font=("Segoe UI", 11, "bold"),
                text_color=THEME["accent_glow"]
            )
            self.thinking_label.pack(padx=14, pady=6)
            self._tick_thinking()

    def _ui_stop_thinking(self):
        if self.thinking_frame and self.thinking_frame.winfo_exists():
            self.thinking_frame.destroy()
            self.thinking_frame = None
            self.thinking_label = None

    def _stop_thinking_animation(self):
        self.after(0, self._ui_stop_thinking)

    def _tick_thinking(self):
        if not self.is_generating or not self.thinking_frame or not self.thinking_label:
            return
        if not self.thinking_label.winfo_exists():
            return
        frame_ch = self.spinner_frames[self.spinner_idx % len(self.spinner_frames)]
        self.spinner_idx += 1
        try:
            self.thinking_label.configure(text=f"{frame_ch}  {self.current_status_text}")
        except Exception:
            pass
        self.after(120, self._tick_thinking)

    def _safe_scroll_down(self):
        try:
            if self.messages_scroll.winfo_exists():
                self.messages_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ================= НАСТРОЙКИ =================
    def open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Параметры окружения PyCodex")
        win.geometry("520x640")
        win.configure(fg_color=THEME["bg_sidebar"])
        win.grab_set()

        providers = load_providers()
        prov_names = list(providers.keys())

        pad_f = ctk.CTkFrame(win, fg_color="transparent")
        pad_f.pack(fill="both", expand=True, padx=25, pady=20)

        ctk.CTkLabel(pad_f, text="Провайдер API", font=("Segoe UI", 12, "bold"), text_color=THEME["text_main"]).pack(anchor="w")
        cmb_prov = ctk.CTkComboBox(pad_f, values=prov_names, fg_color=THEME["bg_card"], border_color=THEME["border"], height=38)
        cmb_prov.set(self.data["settings"].get("provider", prov_names[0]))
        cmb_prov.pack(fill="x", pady=(4, 12))

        ctk.CTkLabel(pad_f, text="API Ключ", font=("Segoe UI", 12, "bold"), text_color=THEME["text_main"]).pack(anchor="w")
        entry_key = ctk.CTkEntry(pad_f, show="*", fg_color=THEME["bg_card"], border_color=THEME["border"], height=38)
        entry_key.insert(0, self.data["settings"].get("api_key", ""))
        entry_key.pack(fill="x", pady=(4, 12))

        ctk.CTkLabel(pad_f, text="Модель", font=("Segoe UI", 12, "bold"), text_color=THEME["text_main"]).pack(anchor="w")
        cmb_model = ctk.CTkComboBox(pad_f, values=[], fg_color=THEME["bg_card"], border_color=THEME["border"], height=38)
        cmb_model.pack(fill="x", pady=(4, 12))

        def on_prov_change(chosen):
            m_list = providers.get(chosen, {}).get("models", [])
            cmb_model.configure(values=m_list)
            if m_list:
                cmb_model.set(m_list[0])

        cmb_prov.configure(command=on_prov_change)
        on_prov_change(cmb_prov.get())
        if self.data["settings"].get("model") in providers.get(cmb_prov.get(), {}).get("models", []):
            cmb_model.set(self.data["settings"].get("model"))

        ctk.CTkLabel(pad_f, text="Режим выполнения", font=("Segoe UI", 12, "bold"), text_color=THEME["text_main"]).pack(anchor="w", pady=(8, 4))
        mode_v = ctk.StringVar(value=self.data["settings"].get("mode", "Default"))
        ctk.CTkRadioButton(pad_f, text="🛡️ Safe Mode (с подтверждением операций)", variable=mode_v, value="Default", text_color=THEME["text_muted"]).pack(anchor="w", pady=2)
        ctk.CTkRadioButton(pad_f, text="⚡ Turbo Mode (полная автономность команд)", variable=mode_v, value="Turbo", text_color=THEME["text_muted"]).pack(anchor="w", pady=2)

        ctk.CTkLabel(pad_f, text="Дополнительный промпт", font=("Segoe UI", 12, "bold"), text_color=THEME["text_main"]).pack(anchor="w", pady=(12, 4))
        txt_sys = ctk.CTkTextbox(pad_f, height=85, fg_color=THEME["bg_card"], border_width=1, border_color=THEME["border"])
        txt_sys.insert("1.0", self.data["settings"].get("custom_prompt", DEFAULT_CUSTOM_PROMPT))
        txt_sys.pack(fill="x")

        def save_and_close():
            self.data["settings"]["provider"] = cmb_prov.get()
            self.data["settings"]["api_key"] = entry_key.get().strip()
            self.data["settings"]["model"] = cmb_model.get()
            self.data["settings"]["mode"] = mode_v.get()
            self.data["settings"]["custom_prompt"] = txt_sys.get("1.0", "end").strip()
            save_data(self.data)
            self._update_badge()
            win.destroy()

        btn_save = ctk.CTkButton(pad_f, text="Применить изменения", font=("Segoe UI", 13, "bold"), fg_color=THEME["accent"], hover_color=THEME["accent_hover"], height=42, command=save_and_close)
        btn_save.pack(fill="x", pady=(20, 0))

if __name__ == "__main__":
    app = PyCodex()
    app.mainloop()
