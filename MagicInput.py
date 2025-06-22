# userinput.py
# Minimalistic popup GUI for entering text/code and attaching images.

import os
import sys
import shutil
import tempfile
import urllib.request
import subprocess
import importlib
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from PIL import Image, ImageTk, ImageGrab
import datetime  # NEW
import platform
import threading
from typing import Optional, Any
import time
import re
import json

# Optional drag-and-drop via tkinterdnd2
DND_SUPPORT = False
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES  # type: ignore
    DND_SUPPORT = True
except ImportError:
    pass

# ------------------------------------------------------------------ DEPENDENCY HANDLING


def _install_and_import(package: str, import_name: str | None = None):
    """Attempt to import a module; if missing, install the package via pip and re-import."""
    name = import_name or package
    try:
        return importlib.import_module(name)
    except ImportError:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package, "--quiet", "--user"])
            return importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            print(f"[MagicInput] Failed to install {package}: {exc}")
            return None


# Pillow (PIL)
PIL_module = _install_and_import("pillow", "PIL")
if PIL_module is None:
    messagebox.showerror("MagicInput", "Required dependency 'pillow' could not be installed. Exiting.")
    sys.exit(1)

from PIL import Image, ImageTk, ImageGrab  # type: ignore  # noqa: E402

import datetime  # NEW
import platform
import threading
from typing import Optional, Any

# At top import section after other imports
# Gemini API (Google Generative AI)
# Try newer google-genai first (stream support), fallback to google-generativeai
genai_stream_module = _install_and_import("google-genai", "google.genai")
gemini_module = None

if genai_stream_module:
    GENAI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if GENAI_API_KEY:
        try:
            # client created later when needed
            pass
        except Exception:
            genai_stream_module = None
else:
    # fallback older sdk
    gemini_module = _install_and_import("google-generativeai", "google.generativeai")
    if gemini_module:
        GENAI_API_KEY = os.environ.get("GEMINI_API_KEY")
        if GENAI_API_KEY:
            gemini_module.configure(api_key=GENAI_API_KEY)
        else:
            gemini_module = None

# On Windows, use ctypes to tweak window styles for task-bar visibility
if platform.system() == 'Windows':
    # Ensure pywin32 (needed for tray icon backend) – actual module is win32api
    _install_and_import("pywin32", "win32api")

    import ctypes  # noqa: E402  (after potential install)
    from ctypes import wintypes  # noqa: E402

# Optional system-tray icon support via pystray
pystray = _install_and_import("pystray")

# ------------------------------------------------------------------ THEME SETTINGS
class Theme:
    """Theme colors and settings for the application."""

    @staticmethod
    def dark():
        """Dark theme - modern dark with vibrant accents."""
        return {
            "bg_main": "#121212",           # Dark background
            "bg_input": "#1E1E1E",          # Slightly lighter input areas
            "bg_header": "#2D2D2D",         # Dark header/title bar
            "text": "#FFFFFF",              # White text
            "fg_header": "#FFFFFF",         # Header text always white
            "text_secondary": "#AAAAAA",    # Light gray secondary text
            "accent_primary": "#BB86FC",    # Purple accent (primary)
            "accent_secondary": "#03DAC5",  # Teal accent (secondary)
            "button_primary": "#BB86FC",    # Purple action buttons
            "button_secondary": "#2D2D2D",  # Gray secondary buttons
            "button_danger": "#CF6679",     # Red/pink for negative actions
            "hover_primary": "#A66AF9",     # Darker purple hover
            "hover_secondary": "#1F1F1F",   # Darker gray hover
            "hover_danger": "#B4475D",      # Darker red hover
            "border": "#333333",            # Dark border
        }

    @staticmethod
    def light():
        """Light theme - clean light with coordinated accents."""
        return {
            "bg_main": "#F5F5F5",          # Light gray background
            "bg_input": "#FFFFFF",          # White input areas
            "bg_header": "#673AB7",         # Deep purple header
            "text": "#212121",              # Almost black text
            "fg_header": "#FFFFFF",         # Header text white on purple
            "text_secondary": "#757575",    # Gray secondary text
            "accent_primary": "#673AB7",    # Deep purple accent (primary)
            "accent_secondary": "#03DAC6",  # Teal accent (secondary)
            "button_primary": "#673AB7",    # Purple action buttons
            "button_secondary": "#E0E0E0",  # Light gray secondary buttons
            "button_danger": "#F44336",     # Red for negative actions
            "hover_primary": "#5E35B1",     # Darker purple hover
            "hover_secondary": "#BDBDBD",   # Darker gray hover
            "hover_danger": "#D32F2F",      # Darker red hover
            "border": "#E0E0E0",            # Light border
        }


class InputPopup:
    """A small, centred popup window that lets the user attach images and enter text/code."""

    CANVAS_HEIGHT = 200

    def __init__(self, root: tk.Tk):
        self.root = root
        # Default to dark theme
        self.current_theme = Theme.dark()
        self.is_dark_theme = True
        # App logo emoji
        self.app_icon_emoji = '🔮'
        self._configure_window()
        self._create_widgets()
        self._layout_widgets()
        if DND_SUPPORT:
            self._enable_dnd()
        # Re-apply frameless after restore from minimize
        self.root.bind("<Map>", self._restore_override)

        # Runtime data
        self.image_paths: list[str] = []
        self.current_index = 0
        self.current_photo: ImageTk.PhotoImage | None = None
        self.temp_dir = tempfile.mkdtemp()
        self.app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        # Folder where all attachments and prompt logs are stored (hidden dot-folder)
        self.attachments_dir = os.path.join(self.app_dir, ".MagicInput")
        os.makedirs(self.attachments_dir, exist_ok=True)
        # Config file path for API keys
        self.config_path = os.path.join(self.attachments_dir, "config.json")
        self.api_key: str | None = None
        # Whether to automatically refine the prompt before sending
        self.auto_refine: bool = False

        # Load existing config (API keys)
        self._load_config()

        # Reconfigure Gemini if key loaded
        if gemini_module and self.api_key:
            try:
                gemini_module.configure(api_key=self.api_key)
            except Exception:
                pass
        self.file_paths: list[str] = []
        self.file_meta: dict[str, tuple[int,int,int]] = {}

        # Create tray icon (Windows only, if pystray available)
        if platform.system() == 'Windows' and pystray is not None:
            self._create_tray_icon()

        # Ensure frameless window still shows in task-bar (Windows only)
        if platform.system() == 'Windows':
            self.root.after(100, self._ensure_taskbar_icon)

    # ------------------------------------------------------------------ UI BUILDERS
    def _configure_window(self) -> None:
        # App metadata
        self.app_name = "MagicInput"

        self.root.title(self.app_name)
        self.root.resizable(False, False)
        # Custom frameless window (no native decorations)
        self.root.overrideredirect(True)
        # Do NOT keep always on top so it can sit behind other windows
        self.root.attributes('-topmost', False)
        
        width, height = 600, 550  # Taller window
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 3
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Apply theme background
        self.root.configure(bg=self.current_theme["bg_main"])
        
        # Configure fonts and styles
        self.title_font = ('Segoe UI', 12, 'bold')
        self.text_font = ('Consolas', 10)
        self.button_font = ('Segoe UI', 10)

        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            style.theme_use("clam")
        # Configure theme-aware TTK styles
        style.configure("TButton", padding=5, 
                       background=self.current_theme["button_secondary"])
        style.configure("TLabel", background=self.current_theme["bg_main"], 
                       foreground=self.current_theme["text"], 
                       font=('Segoe UI', 10))
        style.configure("TFrame", background=self.current_theme["bg_main"])

    def _create_widgets(self) -> None:
        # -------------------- Custom title bar -------------------- #
        self.title_bar = tk.Frame(self.root, bg=self.current_theme["bg_header"], 
                                 relief="flat", height=30)
        # Add emoji as app icon in title bar
        self.icon_lbl = tk.Label(self.title_bar, text=self.app_icon_emoji,
                                 font=('Segoe UI Emoji', 14),
                                 bg=self.current_theme['bg_header'],
                                 fg=self.current_theme['fg_header'])
        self.icon_lbl.pack(side=tk.LEFT, padx=(5, 0))
        self.title_lbl = tk.Label(self.title_bar, text=self.app_name, font=self.title_font,
                                 bg=self.current_theme["bg_header"], 
                                 fg=self.current_theme["fg_header"])

        # Theme toggle button (sun/moon icon)
        theme_icon = "☀" if self.is_dark_theme else "🌙"
        self.theme_btn = tk.Button(self.title_bar, text=theme_icon, 
                                  font=('Segoe UI', 10, 'bold'),
                                  bg=self.current_theme["bg_header"], 
                                  fg=self.current_theme["fg_header"], 
                                  relief="flat",
                                  command=self._toggle_theme)

        # Info (i) button to show developer details
        self.info_btn = tk.Button(self.title_bar, text="i", 
                                 font=('Segoe UI', 10, 'bold'),
                                 bg=self.current_theme["bg_header"], 
                                 fg=self.current_theme["fg_header"], 
                                 relief="flat",
                                 command=self._show_info)

        # Settings (gear) button
        self.settings_btn = tk.Button(self.title_bar, text="⚙", 
                                 font=('Segoe UI', 10, 'bold'),
                                 bg=self.current_theme["bg_header"], 
                                 fg=self.current_theme["fg_header"], 
                                 relief="flat",
                                 command=self._open_settings)

        # Minimize button (–)
        self.minimize_btn = tk.Button(self.title_bar, text="–", 
                                     font=('Segoe UI', 10, 'bold'),
                                     bg=self.current_theme["bg_header"], 
                                     fg=self.current_theme["fg_header"], 
                                     relief="flat",
                                     command=self._minimize)

        # Close button (×)
        self.close_btn = tk.Button(self.title_bar, text="×", 
                                  font=('Segoe UI', 10, 'bold'),
                                  bg=self.current_theme["bg_header"], 
                                  fg=self.current_theme["fg_header"], 
                                  relief="flat",
                                  command=self.root.destroy)

        # Attachment summary (always visible)
        self.attach_summary_var = tk.StringVar(value="")
        self.attach_summary_label = tk.Label(
            self.root,
            textvariable=self.attach_summary_var,
            font=self.text_font,
            bg=self.current_theme["bg_input"],
            fg=self.current_theme["text"],
            anchor="w",
            justify="left"
        )

        # Image preview canvas with better styling
        self.canvas = tk.Canvas(self.root, height=self.CANVAS_HEIGHT, 
                              bg=self.current_theme["bg_input"], 
                              highlightthickness=1, 
                              highlightbackground=self.current_theme["border"])
        # Redraw placeholder when canvas is resized (avoids cropping)
        self.canvas.bind("<Configure>", lambda e: self._draw_placeholder())
        # Initial placeholder draw
        self._draw_placeholder()

        # Image section label
        self.img_label = tk.Label(self.root, text="Image Attachment", 
                                font=self.button_font,
                                bg=self.current_theme["bg_main"], 
                                fg=self.current_theme["text"], 
                                anchor="w")

        # Toolbar for image actions - more colorful buttons
        self.img_bar = tk.Frame(self.root, bg=self.current_theme["bg_main"])
        self.add_btn = tk.Button(self.root, text="Add Image", 
                               bg=self.current_theme["accent_primary"], 
                               fg=self.current_theme["text"], 
                               font=self.button_font, relief="flat", 
                               command=self._add_image)
        self.remove_btn = tk.Button(self.root, text="Remove", 
                                  bg=self.current_theme["button_danger"], 
                                  fg=self.current_theme["text"], 
                                  font=self.button_font, relief="flat", 
                                  command=self._remove_image)
        self.prev_btn = tk.Button(self.root, text="◀", width=3, 
                                bg=self.current_theme["button_secondary"], 
                                fg=self.current_theme["text"], 
                                font=self.button_font, relief="flat", 
                                command=self._prev_image)
        self.next_btn = tk.Button(self.root, text="▶", width=3, 
                                bg=self.current_theme["button_secondary"], 
                                fg=self.current_theme["text"], 
                                font=self.button_font, relief="flat", 
                                command=self._next_image)
        self.counter_var = tk.StringVar(value="0/0")
        self.counter_lbl = tk.Label(self.root, textvariable=self.counter_var,
                                  font=self.button_font, 
                                  bg=self.current_theme["bg_main"], 
                                  fg=self.current_theme["text"])
        self.file_btn = tk.Button(self.root, text="Add File", 
                           bg=self.current_theme["accent_primary"], 
                           fg=self.current_theme["text"], 
                           font=self.button_font, relief="flat", 
                           command=self._add_file)

        # Text section label
        self.text_label = tk.Label(self.root, text="Prompt", 
                                 font=self.button_font,
                                 bg=self.current_theme["bg_main"], 
                                 fg=self.current_theme["text"], 
                                 anchor="w")
        
        # Text / code input without scroll bar, with better font and colors
        self.text_input = tk.Text(
            self.root, wrap=tk.WORD, height=8, font=self.text_font,
            bg=self.current_theme["bg_input"], 
            fg=self.current_theme["text"],
            insertbackground=self.current_theme["accent_primary"]
        )
        self.text_input.bind("<KeyRelease>", self._on_key_release)

        # Bottom buttons container
        self.btn_frame = tk.Frame(self.root, height=50, 
                                 bg=self.current_theme["bg_main"])
        
        # Colored action buttons with hover effect
        self.clear_btn = tk.Button(self.btn_frame, text="Clear", 
                                 font=self.button_font,
                                 bg=self.current_theme["button_secondary"], 
                                 fg=self.current_theme["text"], 
                                 relief="flat", command=self._clear)
        self.send_btn = tk.Button(self.btn_frame, text="Send", 
                                font=self.button_font,
                                bg=self.current_theme["accent_secondary"], 
                                fg=self.current_theme["text"], 
                                relief="flat", command=self._send)
        self.send_close_btn = tk.Button(self.btn_frame, text="Send & Close", 
                                      font=self.button_font,
                                      bg=self.current_theme["accent_primary"], 
                                      fg=self.current_theme["text"], 
                                      relief="flat", 
                                      command=self._send_and_close)
        self.refine_btn = tk.Button(self.btn_frame, text="Refine", 
                               font=self.button_font,
                               bg=self.current_theme["button_secondary"], 
                               fg=self.current_theme["text"], 
                               relief="flat", command=self._refine_prompt)
        
        # Add hover effects
        for btn in (self.add_btn, self.file_btn, self.remove_btn, self.prev_btn, self.next_btn,
                   self.clear_btn, self.refine_btn, self.send_btn, self.send_close_btn, 
                   self.info_btn, self.settings_btn, self.theme_btn, self.minimize_btn, self.close_btn):
            btn.bind("<Enter>", lambda e, b=btn: self._on_hover(b, True))
            btn.bind("<Leave>", lambda e, b=btn: self._on_hover(b, False))

    def _layout_widgets(self) -> None:
        # Title bar layout
        self.title_bar.pack(fill=tk.X)
        self.title_lbl.pack(side=tk.LEFT, padx=10)

        # Attachment summary line
        self.attach_summary_label.pack(fill=tk.X, padx=10, pady=(0, 4))
        self.close_btn.pack(side=tk.RIGHT, padx=5)
        self.minimize_btn.pack(side=tk.RIGHT)
        self.info_btn.pack(side=tk.RIGHT)
        self.settings_btn.pack(side=tk.RIGHT)
        self.theme_btn.pack(side=tk.RIGHT, padx=5)
        
        # Allow dragging window from custom title bar
        self.title_bar.bind("<ButtonPress-1>", self._start_move)
        self.title_bar.bind("<B1-Motion>", self._on_move)

        # Image section
        self.img_label.pack(fill=tk.X, padx=10, pady=(10, 5), anchor="w")
        self.canvas.pack(fill=tk.X, padx=10, pady=(0, 5))

        # Image toolbar
        self.img_bar.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.add_btn.pack(in_=self.img_bar, side=tk.LEFT)
        self.file_btn.pack(in_=self.img_bar, side=tk.LEFT, padx=(5, 0))
        self.remove_btn.pack(in_=self.img_bar, side=tk.LEFT, padx=(5, 0))
        self.prev_btn.pack(in_=self.img_bar, side=tk.RIGHT)
        self.next_btn.pack(in_=self.img_bar, side=tk.RIGHT, padx=(0, 5))
        self.counter_lbl.pack(in_=self.img_bar, side=tk.RIGHT, padx=5)

        # Text section
        self.text_label.pack(fill=tk.X, padx=10, pady=(0, 5), anchor="w")
        self.text_input.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Bottom buttons 
        self.btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.btn_frame.pack_propagate(False)  # Force height
        
        self.clear_btn.pack(side=tk.LEFT, pady=8, ipady=4, ipadx=8)
        self.refine_btn.pack(side=tk.LEFT, padx=(5,0), pady=8, ipady=4, ipadx=8)
        self.send_close_btn.pack(side=tk.RIGHT, pady=8, ipady=4, ipadx=8)
        self.send_btn.pack(side=tk.RIGHT, padx=(0, 5), pady=8, ipady=4, ipadx=8)

        # ------------------------------------------------------------------ KEYBOARD SHORTCUTS
        # Ctrl+Enter -> Send
        self.root.bind_all('<Control-Return>', lambda e: self._send_and_close())
        # Ctrl+V -> Paste image from clipboard
        self.root.bind_all('<Control-v>', lambda e: self._paste_clipboard_image())

    def _enable_dnd(self) -> None:
        # Canvas accepts image files; text area accepts files whose contents are inserted.
        self.canvas.drop_target_register(DND_FILES)  # type: ignore
        self.canvas.dnd_bind("<<Drop>>", self._on_canvas_drop)  # type: ignore
        self.text_input.drop_target_register(DND_FILES)  # type: ignore
        self.text_input.dnd_bind("<<Drop>>", self._on_text_drop)  # type: ignore

    # ------------------------------------------------------------------ IMAGE HANDLING
    def _draw_placeholder(self) -> None:
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or self.canvas.winfo_reqwidth()
        h = self.CANVAS_HEIGHT
        # Draw a nicer placeholder with icon-like appearance
        self.canvas.create_rectangle(w//2-40, h//2-30, w//2+40, h//2+30,
                                   outline=self.current_theme["border"], 
                                   fill=self.current_theme["bg_input"])
        self.canvas.create_line(w//2-20, h//2, w//2+20, h//2, 
                              fill=self.current_theme["text_secondary"])
        self.canvas.create_line(w//2, h//2-20, w//2, h//2+20, 
                              fill=self.current_theme["text_secondary"])
        self.canvas.create_text(w//2, h//2+50, text="Drag & drop image or click 'Add Image'", 
                              fill=self.current_theme["text_secondary"], 
                              font=('Segoe UI', 9))
        self.current_photo = None

    def _update_counter(self) -> None:
        total = len(self.image_paths)
        current = self.current_index + 1 if total else 0
        self.counter_var.set(f"{current}/{total}")

    def _refresh_summary(self) -> None:
        """Update the one-line attachment summary shown under the title bar."""
        parts: list[str] = []
        for p in self.file_paths:
            meta = self.file_meta.get(p)
            if meta:
                s_line, e_line, total = meta
                label = f"📄 {os.path.basename(p)} ({s_line}-{e_line}/{total})"
            else:
                label = f"📄 {os.path.basename(p)}"
            parts.append(label)

        parts.extend("🖼 " + os.path.basename(p) for p in self.image_paths)
        self.attach_summary_var.set("  |  ".join(parts))

    def _add_image(self) -> None:
        paths = filedialog.askopenfilenames(title="Select image(s)", filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp")])
        for p in paths:
            self._store_image(p)
        if paths:
            self.current_index = len(self.image_paths) - 1
            self._show_current_image()
            self._update_counter()
            self._refresh_summary()

    def _store_image(self, src_path: str) -> None:
        try:
            _, ext = os.path.splitext(src_path)
            # Determine next image number based on existing files in folder
            existing_nums = []
            for fname in os.listdir(self.attachments_dir):
                if fname.startswith("MagicInput Image "):
                    try:
                        num_part = fname.split("MagicInput Image ")[1].split(".")[0]
                        existing_nums.append(int(num_part))
                    except (IndexError, ValueError):
                        pass
            next_num = max(existing_nums, default=0) + 1
            dest = os.path.join(self.attachments_dir, f"MagicInput Image {next_num}{ext}")

            shutil.copy(src_path, dest)
            self.image_paths.append(dest)
            # Insert mention into text area at cursor
            self._insert_image_mention(dest)
            self._refresh_summary()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add image: {e}")

    def _show_current_image(self) -> None:
        if not self.image_paths:
            self._draw_placeholder()
            return
        path = self.image_paths[self.current_index]
        try:
            img = Image.open(path)
            # Fit to canvas
            canvas_w = self.canvas.winfo_width() or self.canvas.winfo_reqwidth()
            canvas_h = self.CANVAS_HEIGHT
            img.thumbnail((canvas_w - 4, canvas_h - 4))
            self.current_photo = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=self.current_photo)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot display image: {e}")
            self.image_paths.remove(path)
            self._update_counter()
            self._draw_placeholder()

    def _remove_image(self) -> None:
        if not self.image_paths:
            return
        del self.image_paths[self.current_index]
        self.current_index = max(0, self.current_index - 1)
        self._show_current_image()
        self._update_counter()
        self._refresh_summary()

    def _next_image(self) -> None:
        if not self.image_paths:
            return
        self.current_index = (self.current_index + 1) % len(self.image_paths)
        self._show_current_image()
        self._update_counter()

    def _prev_image(self) -> None:
        if not self.image_paths:
            return
        self.current_index = (self.current_index - 1) % len(self.image_paths)
        self._show_current_image()
        self._update_counter()

    def _add_file(self) -> None:
        paths = filedialog.askopenfilenames(title="Select file(s)", initialdir=self.app_dir)
        for p in paths:
            self._store_file(p)

    def _store_file(self, src_path: str) -> None:
        try:
            _, ext = os.path.splitext(src_path)
            existing_nums = []
            for fname in os.listdir(self.attachments_dir):
                if fname.startswith("MagicInput File "):
                    try:
                        num_part = fname.split("MagicInput File ")[1].split(".")[0]
                        existing_nums.append(int(num_part))
                    except (IndexError, ValueError):
                        pass
            next_num = max(existing_nums, default=0) + 1
            dest = os.path.join(self.attachments_dir, f"MagicInput File {next_num}{ext}")
            shutil.copy(src_path, dest)
            self.file_paths.append(dest)
            # Insert a mention into the prompt so the user can reference it easily
            self._insert_file_mention(dest)
            self._refresh_summary()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add file: {e}")

    # ------------------------------------------------------------------ DRAG-AND-DROP EVENTS
    def _on_canvas_drop(self, event):  # noqa: N802 (tkinter callback name)
        for filepath in self.root.tk.splitlist(event.data):
            lower = filepath.lower()
            if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
                self._store_image(filepath)
            else:
                self._store_file(filepath)
        if self.image_paths:
            self.current_index = len(self.image_paths) - 1
            self._show_current_image()
            self._update_counter()
            self._refresh_summary()

    def _on_text_drop(self, event):  # noqa: N802
        filepath = self.root.tk.splitlist(event.data)[0]
        if os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    self.text_input.insert(tk.END, f.read())
            except Exception as e:
                messagebox.showerror("Error", f"Cannot read file: {e}")

    # ------------------------------------------------------------------ BUTTON COMMANDS
    def _clear(self) -> None:
        if messagebox.askyesno("Confirm", "Clear all inputs?"):
            self.image_paths.clear()
            self.current_index = 0
            self.text_input.delete("1.0", tk.END)
            self._draw_placeholder()
            self._update_counter()
            self._refresh_summary()

    def _collect_data(self) -> str:
        """Gather user input and attachment paths as formatted text."""
        text = self.text_input.get("1.0", tk.END).strip()

        # ----------------------------------------------------
        # Append footer directive based on attachment types
        # ----------------------------------------------------
        footer_parts: list[str] = []

        # Determine if any images are present
        if self.image_paths:
            footer_parts.append("screenshot/image")

        # Classify files between code and other attachments
        code_exts = {
            ".py", ".js", ".ts", ".tsx", ".jsx", ".c", ".cpp", ".h", ".hpp", ".cs", ".java",
            ".rb", ".go", ".rs", ".swift", ".kt", ".kts", ".php", ".pl", ".sh", ".bat", ".cmd",
            ".sql", ".xml", ".json", ".yaml", ".yml", ".css", ".scss", ".html", ".htm", ".md",
            ".txt",
        }

        code_found = False
        other_found = False
        for p in self.file_paths:
            _, ext = os.path.splitext(p)
            if ext.lower() in code_exts:
                code_found = True
            else:
                other_found = True

        if code_found:
            footer_parts.append("Code/file")
        if other_found and not code_found:
            # Only non-code files present ➔ treat as generic attachment
            footer_parts.append("attachement")
        elif other_found and code_found:
            # Both code and other attachment types present ➔ mention both
            footer_parts.append("attachement")

        # Build footer sentence
        footer_line = ""
        if footer_parts:
            if len(footer_parts) == 1:
                parts_str = footer_parts[0]
            else:
                parts_str = " and ".join(footer_parts)
            footer_line = f"read the {parts_str} (fllowing the direcotry link) mention above."

        if footer_line:
            text = f"{text}\n{footer_line}" if text else footer_line

        lines: list[str] = []
        lines.append("Prompt:")
        lines.append(text)

        if self.file_paths:
            lines.append("")  # blank line before attachment section
            lines.append("Attachments:")
            # only files (exclude images — they are already mentioned inline)
            for p in self.file_paths:
                meta = self.file_meta.get(p)
                if meta:
                    s_line, e_line, total = meta
                    extra = f" ({s_line}-{e_line}/{total})"
                else:
                    extra = ""
                lines.append("@" + os.path.abspath(p) + extra)

        return "\n".join(lines)

    def _send(self) -> None:
        # Auto-refine prompt before processing if enabled
        if getattr(self, "auto_refine", False):
            self._refine_prompt()

        # Attempt to auto-detect file matches for pasted snippet
        self._detect_snippet_files()
        self._extract_mentioned_files()
        collected = self._collect_data()
        # Print to terminal
        print(collected)
        sys.stdout.flush()
        # Prompt user to rerun and get response
        print("**To get user response and after completeting the task run again python MagicInput.py. Follow the user rule always**")

        # Persist the collected input to a single file inside the folder
        log_path = os.path.join(self.attachments_dir, "MagicInput Prompt.txt")
        try:
            # Append with a separator for readability
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(collected + "\n\n")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write prompt file: {e}")

    def _send_and_close(self) -> None:
        self._send()
        self.root.after(100, self.root.destroy)

    # ------------------------------------------------------------------ CLEANUP
    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

        # Stop tray icon if running
        if hasattr(self, "tray_icon") and self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass

    def _on_hover(self, button, entering):
        """Handle hover effect for buttons"""
        current_bg = button["bg"]
        # Compare with theme colors for proper hover effect
        if entering:  # Mouse entering - adjust color
            if current_bg == self.current_theme["accent_primary"]:
                button["bg"] = self.current_theme["hover_primary"]
            elif current_bg == self.current_theme["accent_secondary"]:
                button["bg"] = self.current_theme["hover_secondary"]
            elif current_bg == self.current_theme["button_danger"]:
                button["bg"] = self.current_theme["hover_danger"]
            elif current_bg == self.current_theme["button_secondary"]:
                button["bg"] = self.current_theme["hover_secondary"]
            elif current_bg == self.current_theme["bg_header"]:
                button["bg"] = self.current_theme["hover_secondary"]
        else:  # Mouse leaving - restore
            if current_bg == self.current_theme["hover_primary"]:
                button["bg"] = self.current_theme["accent_primary"]
            elif current_bg == self.current_theme["hover_secondary"] and button == self.send_btn:
                button["bg"] = self.current_theme["accent_secondary"]
            elif current_bg == self.current_theme["hover_danger"]:
                button["bg"] = self.current_theme["button_danger"]
            elif current_bg == self.current_theme["hover_secondary"] and button in [self.prev_btn, self.next_btn, self.clear_btn]:
                button["bg"] = self.current_theme["button_secondary"]
            elif current_bg == self.current_theme["hover_secondary"] and button in [self.info_btn, self.settings_btn, self.theme_btn, self.minimize_btn, self.close_btn]:
                button["bg"] = self.current_theme["bg_header"]

    # ------------------------------------------------------------------ INFO POPUP
    def _show_info(self) -> None:
        # Show custom themed info dialog instead of default messagebox
        info_text = (
            "Developer: Badiuzzaman Majnu\n"
            "Professional Graphics Designer, Developer, Freelancer.\n\n"
            "WhatsApp: +8801796072129\n"
            "Facebook: https://www.facebook.com/bmajnu786\n"
            "Email: badiuzzamanmajnu786@gmail.com"
        )
        popup = tk.Toplevel(self.root)
        popup.title(self.app_name)
        popup.configure(bg=self.current_theme["bg_main"])
        popup.transient(self.root)
        popup.resizable(False, False)
        # Remove native window decorations
        popup.overrideredirect(True)
        # Content frame
        frame = tk.Frame(popup, bg=self.current_theme["bg_main"])
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        # Info label
        label = tk.Label(
            frame, text=info_text,
            bg=self.current_theme["bg_main"],
            fg=self.current_theme["text"],
            font=self.text_font,
            justify="left",
            wraplength=360
        )
        label.pack(fill="both", expand=True)
        # OK button
        btn = tk.Button(
            frame, text="OK",
            bg=self.current_theme["accent_primary"],
            fg=self.current_theme["fg_header"],
            font=self.button_font,
            relief="flat",
            command=popup.destroy
        )
        btn.pack(pady=(10, 0))
        # Hover effect
        btn.bind("<Enter>", lambda e: btn.config(bg=self.current_theme["hover_primary"]))
        btn.bind("<Leave>", lambda e: btn.config(bg=self.current_theme["accent_primary"]))

        # Allow dragging the popup by holding anywhere inside
        _drag_data = {"x": 0, "y": 0}

        def _start_drag(evt):
            _drag_data["x"] = evt.x
            _drag_data["y"] = evt.y

        def _on_drag(evt):
            x = evt.x_root - _drag_data["x"]
            y = evt.y_root - _drag_data["y"]
            popup.geometry(f"+{x}+{y}")

        popup.bind("<ButtonPress-1>", _start_drag)
        popup.bind("<B1-Motion>", _on_drag)

        # Close on Esc key
        popup.bind("<Escape>", lambda e: popup.destroy())

        # Centre relative to the parent window (works even for frameless root)
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        x = root_x + (self.root.winfo_width() - popup.winfo_width()) // 2
        y = root_y + (self.root.winfo_height() - popup.winfo_height()) // 2
        popup.geometry(f"+{x}+{y}")

        # Bring popup to front reliably
        popup.lift()
        popup.attributes('-topmost', True)
        popup.after(200, lambda: popup.attributes('-topmost', False))
        popup.focus_force()

    # ------------------------------------------------------------------ WINDOW DRAGGING
    def _start_move(self, event):  # noqa: N802
        self._x_offset = event.x
        self._y_offset = event.y

    def _on_move(self, event):  # noqa: N802
        x = event.x_root - getattr(self, '_x_offset', 0)
        y = event.y_root - getattr(self, '_y_offset', 0)
        self.root.geometry(f"+{x}+{y}")

    def _paste_clipboard_image(self) -> None:
        """Attempt to paste an image from the system clipboard (Ctrl+V)."""
        try:
            data = ImageGrab.grabclipboard()
            if isinstance(data, Image.Image):
                # Save clipboard image to a temporary file then store
                temp_path = os.path.join(self.temp_dir, "clipboard_image.png")
                data.save(temp_path, format="PNG")
                self._store_image(temp_path)
            elif isinstance(data, list):
                # Clipboard may contain file paths
                for p in data:
                    if os.path.isfile(p):
                        self._store_image(p)
            else:
                return  # Clipboard doesn't contain an image

            if self.image_paths:
                self.current_index = len(self.image_paths) - 1
                self._show_current_image()
                self._update_counter()
                self._refresh_summary()
        except Exception as e:
            messagebox.showerror("Error", f"Cannot paste image from clipboard: {e}")

    # ------------------------------------------------------------------ WINDOW CONTROL METHODS
    def _minimize(self):
        """Minimize window while temporarily disabling overrideredirect."""
        # Turn off frameless to allow minimization
        self.root.overrideredirect(False)
        self.root.iconify()

    def _restore_override(self, event=None):  # noqa: D401
        """Re-apply overrideredirect after window is restored from iconify."""
        if self.root.state() == 'normal':
            self.root.overrideredirect(True)
            # Re-apply style to ensure taskbar icon persists
            if platform.system() == 'Windows':
                self._ensure_taskbar_icon()

    # ------------------------------------------------------------------ PLATFORM HELPERS

    def _ensure_taskbar_icon(self):
        """On Windows, adjust window styles so override-redirect window is shown in task-bar."""
        try:
            if platform.system() != 'Windows':
                return

            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000

            hwnd = self.root.winfo_id()
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # Remove TOOLWINDOW and add APPWINDOW
            style = style & ~WS_EX_TOOLWINDOW | WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

        except Exception:
            # Fail silently if ctypes operations not permitted
            pass

    # ------------------------------------------------------------------ TRAY ICON

    def _create_tray_icon(self):
        """Create a system-tray icon with Show and Exit actions using the magic emoji."""
        if pystray is None:
            return
        from PIL import ImageDraw, ImageFont

        # Create an RGBA image for the emoji icon
        size = 64
        bg = self.current_theme.get('accent_primary', '#BB86FC')
        fg = self.current_theme.get('fg_header', '#FFFFFF')
        img = Image.new('RGBA', (size, size), bg)
        draw = ImageDraw.Draw(img)

        # Load system emoji font on Windows
        font = None
        if os.name == 'nt':
            # Use raw string for default Windows directory to avoid escape-sequence warning
            font_path = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'seguiemj.ttf')
            try:
                font = ImageFont.truetype(font_path, 48)
            except Exception:
                font = None
        if font is None:
            font = ImageFont.load_default()

        # Draw the emoji centered
        text = self.app_icon_emoji
        # Measure the size of the emoji text
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((size - w) / 2, (size - h) / 2), text, font=font, fill=fg)

        # Build tray menu
        menu = pystray.Menu(
            pystray.MenuItem('Show', lambda: self._show_window(), default=True),
            pystray.MenuItem('Exit', lambda: self.root.after(0, self.root.destroy))
        )

        # Start the tray icon
        self.tray_icon = pystray.Icon('MagicInput', img, 'MagicInput', menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _show_window(self):
        """Restore and focus the window from the tray."""
        self.root.deiconify()
        # Bring window to the front reliably
        self.root.attributes('-topmost', True)
        self.root.lift()
        self.root.focus_force()
        # Disable always-on-top again to preserve user stacking order
        self.root.after(200, lambda: self.root.attributes('-topmost', False))

    # ------------------------------------------------------------------ THEME TOGGLING

    def _toggle_theme(self):
        """Switch between dark and light themes."""
        self.is_dark_theme = not self.is_dark_theme
        self.current_theme = Theme.dark() if self.is_dark_theme else Theme.light()
        
        # Update the theme toggle button icon
        self.theme_btn.config(text="☀" if self.is_dark_theme else "🌙")
        
        # Update main window
        self.root.configure(bg=self.current_theme["bg_main"])
        
        # Update title bar
        title_bar_widgets = [self.title_bar, self.title_lbl, self.theme_btn, 
                           self.info_btn, self.minimize_btn, self.close_btn]
        for widget in title_bar_widgets:
            widget.configure(bg=self.current_theme["bg_header"])
            if widget != self.title_bar:
                widget.configure(fg=self.current_theme["fg_header"])
                
        # Update main content
        content_labels = [self.img_label, self.counter_lbl, self.text_label]
        # include summary label as content label so its colors update
        content_labels.append(self.attach_summary_label)
        for label in content_labels:
            label.configure(bg=self.current_theme["bg_main"], fg=self.current_theme["text"])
            
        # Update frames
        frames = [self.btn_frame, self.img_bar]
        for frame in frames:
            frame.configure(bg=self.current_theme["bg_main"])
            
        # Update canvas
        self.canvas.configure(bg=self.current_theme["bg_input"], 
                            highlightbackground=self.current_theme["border"])
        self._draw_placeholder()
        
        # Update text input
        self.text_input.configure(bg=self.current_theme["bg_input"], 
                                fg=self.current_theme["text"],
                                insertbackground=self.current_theme["accent_primary"])
        
        # Update buttons with appropriate colors
        self.add_btn.configure(bg=self.current_theme["accent_primary"], 
                              fg=self.current_theme["text"])
        self.remove_btn.configure(bg=self.current_theme["button_danger"], 
                                fg=self.current_theme["text"])
        self.prev_btn.configure(bg=self.current_theme["button_secondary"], 
                               fg=self.current_theme["text"])
        self.next_btn.configure(bg=self.current_theme["button_secondary"], 
                               fg=self.current_theme["text"])
        self.clear_btn.configure(bg=self.current_theme["button_secondary"], 
                                fg=self.current_theme["text"])
        self.send_btn.configure(bg=self.current_theme["accent_secondary"], 
                               fg=self.current_theme["text"])
        self.send_close_btn.configure(bg=self.current_theme["accent_primary"], 
                                     fg=self.current_theme["text"])
        self.refine_btn.configure(bg=self.current_theme["button_secondary"], fg=self.current_theme["text"])

    def _on_key_release(self, event) -> None:  # noqa: N802
        """Detect '@' key to trigger file autocomplete popup."""
        if event.char == "@":
            self._show_file_autocomplete()

        # Debounced snippet detection – run at most once per second
        now = time.time()
        last = getattr(self, "_last_snippet_scan", 0)
        if now - last > 1.0:
            self._last_snippet_scan = now
            self._detect_snippet_files()

        # Live extraction of @file mentions to update summary
        self._extract_mentioned_files()

    def _show_file_autocomplete(self) -> None:
        """Popup a listbox with files from app directory; insert selection after '@'."""
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.configure(bg=self.current_theme["bg_main"])

        # Position the popup right under the insertion cursor
        bbox = self.text_input.bbox(tk.INSERT)
        if bbox:
            x, y, width, height = bbox
            # Convert widget coords to root coords
            widget_x = self.text_input.winfo_rootx()
            widget_y = self.text_input.winfo_rooty()
            popup.geometry(f"200x150+{widget_x + x}+{widget_y + y + height}")
        else:
            popup.geometry("200x150")

        lb = tk.Listbox(popup, bg=self.current_theme["bg_input"], fg=self.current_theme["text"],
                        selectbackground=self.current_theme["accent_primary"], highlightthickness=0)
        lb.pack(fill=tk.BOTH, expand=True)

        entries = sorted(os.listdir(self.app_dir))
        for entry in entries:
            full_path = os.path.join(self.app_dir, entry)
            icon = "📁 " if os.path.isdir(full_path) else "📄 "
            lb.insert(tk.END, icon + entry)

        def _insert(event=None):
            raw = lb.get(tk.ACTIVE)
            if raw:
                # Remove the icon prefix (first two chars + space)
                selection = raw[2:] if raw.startswith(("📁", "📄")) else raw
                self.text_input.insert(tk.INSERT, selection)
            popup.destroy()

        lb.bind("<Double-Button-1>", _insert)
        lb.bind("<Return>", _insert)
        lb.focus_set()

        # Close on escape or click outside
        lb.bind("<Escape>", lambda e: popup.destroy())
        popup.bind("<FocusOut>", lambda e: popup.destroy())

    def _detect_snippet_files(self) -> None:
        """Try to locate files in the codebase that contain the pasted snippet and add them as attachments."""
        snippet = self.text_input.get("1.0", tk.END).strip()
        # Skip if snippet too short
        if len(snippet) < 15:
            return

        matches: list[str] = []
        for root, _dirs, files in os.walk(self.app_dir):
            # Skip the internal .MagicInput directory
            if os.path.basename(root) == ".MagicInput":
                continue
            for name in files:
                path = os.path.join(root, name)
                # Limit to text-like files < 1MB to keep things responsive
                try:
                    if os.path.getsize(path) > 1_000_000:
                        continue
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        if snippet in f.read():
                            matches.append(path)
                except Exception:
                    continue
        if not matches:
            return
        selected: str | None = None
        if len(matches) == 1:
            selected = matches[0]
        else:
            # Ask user to choose
            selected = self._ask_user_to_choose_file(matches)
        if selected and selected not in self.file_paths:
            self.file_paths.append(selected)
            # calculate meta for selected
            try:
                with open(selected, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                total_lines = content.count("\n") + 1
                idx = content.find(snippet)
                if idx != -1:
                    pre = content[:idx]
                    start_line = pre.count("\n") + 1
                    snippet_line_count = snippet.count("\n") + 1
                    end_line = start_line + snippet_line_count - 1
                    self.file_meta[selected] = (start_line, end_line, total_lines)
                    # Replace snippet in UI with mention
                    self._replace_snippet_with_mention(snippet, selected, self.file_meta[selected])
            except Exception:
                pass

            self._refresh_summary()

    def _extract_mentioned_files(self) -> None:
        """Synchronise self.file_paths with the @file mentions currently present in the text box."""
        text = self.text_input.get("1.0", tk.END)

        # Gather all mentioned file tokens (could be absolute or relative)
        mentioned_tokens = re.findall(r"@([\w./\\-]+)", text)
        mentioned_abs: set[str] = set()
        for token in mentioned_tokens:
            if os.path.isabs(token):
                mentioned_abs.add(os.path.abspath(token))
            else:
                mentioned_abs.add(os.path.abspath(os.path.join(self.app_dir, token)))

        # Add newly mentioned files
        for abs_path in mentioned_abs:
            if os.path.isfile(abs_path) and abs_path not in self.file_paths:
                self.file_paths.append(abs_path)

        # Remove files no longer mentioned
        for existing in self.file_paths[:]:
            if existing not in mentioned_abs:
                self.file_paths.remove(existing)
                self.file_meta.pop(existing, None)

        # Finally refresh summary bar
        self._refresh_summary()

    def _ask_user_to_choose_file(self, options: list[str]) -> str | None:
        """Popup list for user to choose one of the matching files."""
        popup = tk.Toplevel(self.root)
        popup.title("Select matching file")
        popup.configure(bg=self.current_theme["bg_main"])
        popup.geometry("400x250")
        lb = tk.Listbox(popup, bg=self.current_theme["bg_input"], fg=self.current_theme["text"],
                        selectbackground=self.current_theme["accent_primary"], highlightthickness=0)
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for path in options:
            lb.insert(tk.END, path)

        chosen: list[str] = []

        def _choose(event=None):
            sel = lb.get(tk.ACTIVE)
            if sel:
                chosen.append(sel)
            popup.destroy()

        lb.bind("<Double-Button-1>", _choose)
        lb.bind("<Return>", _choose)
        lb.focus_set()
        popup.bind("<Escape>", lambda e: popup.destroy())
        popup.wait_window()
        return chosen[0] if chosen else None

    def _replace_snippet_with_mention(self, snippet: str, file_path: str, meta: tuple[int, int, int]):
        """Replace the first occurrence of the snippet in the text box with a formatted mention line."""
        s_line, e_line, total = meta
        # Build preview words
        words = snippet.strip().split()
        first_two = " ".join(words[:2])
        last_two = " ".join(words[-2:]) if len(words) > 2 else ""
        preview = f"{first_two} … {last_two}" if last_two else first_two
        # Include the relative path so the directory link is visible to the user
        rel_path = os.path.relpath(file_path, self.app_dir)
        mention_line = f"[@{rel_path} ({s_line}-{e_line}/{total}) «{preview}»]"

        # Use Tk search to locate snippet text
        pos = self.text_input.search(snippet, "1.0", tk.END)
        if pos:
            end_pos = f"{pos}+{len(snippet)}c"
            self.text_input.delete(pos, end_pos)
            self.text_input.insert(pos, mention_line)

            # Ensure summary bar refreshes
            self._extract_mentioned_files()
            self._refresh_summary()

    def _insert_image_mention(self, img_path: str) -> None:
        """Insert an image mention tag at the current cursor location."""
        # Show the relative path (inside .MagicInput) so users can click/see the directory link
        rel_path = os.path.relpath(img_path, self.app_dir)
        mention = f"[🖼 {rel_path}]"
        self.text_input.insert(tk.INSERT, mention + "\n")

    def _insert_file_mention(self, file_path: str) -> None:
        """Insert a file mention tag (with path) at the current cursor location."""
        rel_path = os.path.relpath(file_path, self.app_dir)
        self.text_input.insert(tk.INSERT, f"[@{rel_path}]\n")

    def _refine_prompt(self) -> None:
        """Use Gemini AI to rewrite/refine the current prompt text."""
        if (genai_stream_module is None and gemini_module is None) or not self.api_key:
            messagebox.showwarning("Gemini API","Gemini AI not configured. Please set the API key via Settings (⚙) or GEMINI_API_KEY env var.")
            return
        original = self.text_input.get("1.0", tk.END).strip()
        if not original:
            return
        # Build context from attachments
        context_parts: list[str] = []
        for img in self.image_paths:
            context_parts.append(f"Image: {os.path.basename(img)} (path: {img})")
        for p in self.file_paths:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    # Feed the entire file to the LLM so it has full context (the model will handle truncation if needed).
                    content = f.read()
                context_parts.append(f"File: {os.path.basename(p)}\n---\n{content}\n---")
            except Exception:
                continue
        context_block = "\n\n".join(context_parts) if context_parts else ""

        self.refine_btn.config(state=tk.DISABLED)
        self.root.config(cursor="wait")
        self.root.update()
        try:
            prompt_text = (
                "Act like ai code assistant. Your task to rewrite the USER_PROMPT below into a concise, well-structured and professional prompt. "
                "Use ONLY the information supplied – USER_PROMPT and ATTACHMENT_CONTEXT – and DO NOT ask the user for any additional details. "
                "If critical information is missing, leave a short TODO placeholder rather than requesting it. "
                "Do not add any additional comments or explanations.\n\n"
                f"USER_PROMPT:\n{original}\n\n" + (f"ATTACHMENT_CONTEXT:\n{context_block}" if context_block else "")
            )

            refined = None
            if genai_stream_module and self.api_key:
                client = genai_stream_module.Client(api_key=self.api_key)
                contents = [genai_stream_module.types.Content(role="user", parts=[genai_stream_module.types.Part.from_text(text=prompt_text)])]
                cfg = genai_stream_module.types.GenerateContentConfig(response_mime_type="text/plain")
                chunks = client.models.generate_content_stream(model="gemini-2.5-flash", contents=contents, config=cfg)
                refined_parts: list[str] = []
                for ch in chunks:
                    txt = getattr(ch, "text", None)
                    if isinstance(txt, str):
                        refined_parts.append(txt)
                refined = "".join(refined_parts)
            elif gemini_module and self.api_key:
                model = gemini_module.GenerativeModel("gemini-pro")
                response = model.generate_content(prompt_text)
                refined = getattr(response, "text", None)

            if not refined:
                refined = original
            self.text_input.delete("1.0", tk.END)
            self.text_input.insert("1.0", refined)
        except Exception as e:
            messagebox.showerror("Gemini Error", f"Failed to refine prompt: {e}")
        finally:
            self.refine_btn.config(state=tk.NORMAL)
            self.root.config(cursor="")

    # Add config load/save and settings dialog methods near other helpers
    def _load_config(self):
        try:
            if os.path.isfile(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.api_key = data.get("gemini_api_key")
                    self.auto_refine = data.get("auto_refine", False)
        except Exception:
            pass

    def _save_config(self):
        data = {"gemini_api_key": self.api_key, "auto_refine": self.auto_refine}
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            messagebox.showerror("Config Error", f"Unable to save config: {e}")

    def _open_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.configure(bg=self.current_theme["bg_main"])
        dialog.resizable(False, False)
        # API key label & entry
        tk.Label(dialog, text="Gemini API Key:", bg=self.current_theme["bg_main"], fg=self.current_theme["text"]).pack(padx=10, pady=(10,0), anchor="w")
        key_var = tk.StringVar(value=self.api_key or "")
        entry = tk.Entry(dialog, textvariable=key_var, width=50, show="*", bg=self.current_theme["bg_input"], fg=self.current_theme["text"])
        entry.pack(padx=10, pady=5)

        # Auto refine checkbox
        auto_var = tk.BooleanVar(value=self.auto_refine)
        chk = tk.Checkbutton(
            dialog,
            text="Auto refine prompt before send",
            variable=auto_var,
            bg=self.current_theme["bg_main"],
            fg=self.current_theme["text"],
            selectcolor=self.current_theme["bg_main"],
            activebackground=self.current_theme["bg_main"],
            activeforeground=self.current_theme["text"]
        )
        chk.pack(padx=10, pady=(0, 10), anchor="w")

        def _save():
            self.api_key = key_var.get().strip()
            self.auto_refine = auto_var.get()
            self._save_config()
            if gemini_module and self.api_key:
                try:
                    gemini_module.configure(api_key=self.api_key)
                except Exception as e:
                    messagebox.showerror("Gemini", f"Failed to configure Gemini: {e}")
            dialog.destroy()

        btn = tk.Button(dialog, text="Save", command=_save, bg=self.current_theme["accent_primary"], fg=self.current_theme["fg_header"], relief="flat")
        btn.pack(pady=(0,10))

        dialog.grab_set()


# ---------------------------------------------------------------------- entry-point

def main() -> None:
    if DND_SUPPORT:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = InputPopup(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()