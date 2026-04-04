"""
Mass Torrent Loader — Bulk-load .torrent files into qBittorrent via Web API.
Supports local file loading and RSS feed downloading.
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

import config_manager as cfg
from qbit_client import QBitClient
from rss_fetcher import fetch_feed, extract_smart_name, download_torrent

# DPI awareness on Windows
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class MassTorrentLoader:
    def __init__(self, root):
        self.root = root
        self.root.title("Mass Torrent Loader")
        self.root.resizable(True, True)
        self.root.minsize(650, 750)

        self.config = cfg.load_config()
        self.selected_files = []
        self.original_files = []
        self.qbit = None
        self.category_paths = {}  # {name: save_path} from qBit
        self.cancel_event = threading.Event()
        self.loading = False

        # RSS state
        self.rss_entries = []  # list of {title, download_url, size}
        self.rss_check_vars = []  # list of BooleanVar for checkboxes
        self.rss_smart_name = ""
        self.rss_cancel_event = threading.Event()

        self._build_ui()
        self._load_config_to_ui()

        # Auto-connect on startup using saved credentials
        self.root.after(100, self._test_connection)

    # ═══════════════════════════════════════════════════════════════
    # UI Construction
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # ─── Connection (shared) ────────────────────────────────
        conn_frame = ttk.LabelFrame(main, text="Connection", padding=8)
        conn_frame.pack(fill=tk.X, **pad)

        row1 = ttk.Frame(conn_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Host:").pack(side=tk.LEFT)
        self.host_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.host_var, width=20).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(row1, text="Port:").pack(side=tk.LEFT)
        self.port_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.port_var, width=8).pack(side=tk.LEFT, padx=(4, 0))

        row2 = ttk.Frame(conn_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="User:").pack(side=tk.LEFT)
        self.user_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.user_var, width=20).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(row2, text="Pass:").pack(side=tk.LEFT)
        self.pass_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.pass_var, width=20, show="*").pack(side=tk.LEFT, padx=(4, 12))
        self.test_btn = ttk.Button(row2, text="Test", command=self._test_connection)
        self.test_btn.pack(side=tk.LEFT)

        self.conn_status = ttk.Label(conn_frame, text="Not connected", foreground="gray")
        self.conn_status.pack(anchor=tk.W, pady=(4, 0))

        # ─── Tabs ───────────────────────────────────────────────
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True, **pad)

        self._build_file_loader_tab()
        self._build_rss_tab()

        # ─── Log (shared) ──────────────────────────────────────
        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, **pad)

        self.log_text = tk.Text(log_frame, height=8, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 9))
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text.tag_configure("ok", foreground="#2e7d32")
        self.log_text.tag_configure("skip", foreground="#e65100")
        self.log_text.tag_configure("error", foreground="#c62828")
        self.log_text.tag_configure("info", foreground="#1565c0")

    # ─── File Loader Tab ────────────────────────────────────────

    def _build_file_loader_tab(self):
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="File Loader")

        # Source
        src_frame = ttk.LabelFrame(tab, text="Torrent Source", padding=8)
        src_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        btn_row = ttk.Frame(src_frame)
        btn_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(btn_row, text="Browse Files...", command=self._browse_files).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Remove Selected", command=self._remove_selected_files).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(btn_row, text="Remove All", command=self._remove_all_files).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(btn_row, text="Sort:").pack(side=tk.LEFT, padx=(12, 2))
        self.sort_var = tk.StringVar(value="Original Sequence")
        sort_combo = ttk.Combobox(btn_row, textvariable=self.sort_var,
                                   values=["Original Sequence", "Alphabetically"],
                                   state="readonly", width=16)
        sort_combo.pack(side=tk.LEFT)
        sort_combo.bind("<<ComboboxSelected>>", self._on_sort_changed)
        self.file_count_label = ttk.Label(btn_row, text="No files selected")
        self.file_count_label.pack(side=tk.LEFT, padx=12)

        list_frame = ttk.Frame(src_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, height=6)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        if HAS_DND:
            self.file_listbox.drop_target_register(DND_FILES)
            self.file_listbox.dnd_bind("<<Drop>>", self._on_drop)
            self.file_count_label.configure(text="No files selected \u2014 browse or drag && drop")

        # Destination
        dest_frame = ttk.LabelFrame(tab, text="Destination", padding=8)
        dest_frame.pack(fill=tk.X, padx=4, pady=4)

        preset_row = ttk.Frame(dest_frame)
        preset_row.pack(fill=tk.X, pady=2)
        ttk.Label(preset_row, text="Preset:").pack(side=tk.LEFT)
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_row, textvariable=self.preset_var, state="readonly", width=30)
        self.preset_combo.pack(side=tk.LEFT, padx=(4, 8))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)
        ttk.Button(preset_row, text="Save", command=self._save_preset).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_row, text="Delete", command=self._delete_preset).pack(side=tk.LEFT, padx=2)

        cat_row = ttk.Frame(dest_frame)
        cat_row.pack(fill=tk.X, pady=2)
        ttk.Label(cat_row, text="Category:").pack(side=tk.LEFT)
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(cat_row, textvariable=self.category_var, width=30)
        self.category_combo.pack(side=tk.LEFT, padx=(4, 4))
        self.category_combo.bind("<<ComboboxSelected>>", self._on_fl_category_selected)
        ttk.Button(cat_row, text="Refresh", command=self._refresh_categories).pack(side=tk.LEFT)

        path_row = ttk.Frame(dest_frame)
        path_row.pack(fill=tk.X, pady=2)
        ttk.Label(path_row, text="Save Path:").pack(side=tk.LEFT)
        self.savepath_var = tk.StringVar()
        ttk.Entry(path_row, textvariable=self.savepath_var, width=40).pack(side=tk.LEFT, padx=(4, 8), fill=tk.X, expand=True)
        ttk.Button(path_row, text="Browse", command=self._browse_savepath).pack(side=tk.LEFT)

        # Options
        opt_frame = ttk.LabelFrame(tab, text="Options", padding=8)
        opt_frame.pack(fill=tk.X, padx=4, pady=4)

        opt_row = ttk.Frame(opt_frame)
        opt_row.pack(fill=tk.X)
        ttk.Label(opt_row, text="Delay between adds:").pack(side=tk.LEFT)
        self.delay_var = tk.StringVar()
        ttk.Entry(opt_row, textvariable=self.delay_var, width=6).pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(opt_row, text="sec").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(opt_row, text="Save", command=self._save_options).pack(side=tk.LEFT)

        pause_row = ttk.Frame(opt_frame)
        pause_row.pack(fill=tk.X, pady=(4, 0))
        self.paused_var = tk.BooleanVar()
        ttk.Checkbutton(pause_row, text="Add paused, then resume in batches of", variable=self.paused_var).pack(side=tk.LEFT)
        self.batch_var = tk.StringVar()
        ttk.Entry(pause_row, textvariable=self.batch_var, width=4).pack(side=tk.LEFT, padx=(4, 0))

        # Action bar
        action_frame = ttk.Frame(tab, padding=(0, 8))
        action_frame.pack(fill=tk.X)

        self.start_btn = ttk.Button(action_frame, text="Start Loading", command=self._start_loading)
        self.start_btn.pack(side=tk.LEFT)
        self.cancel_btn = ttk.Button(action_frame, text="Cancel", command=self._cancel_loading, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=8)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(action_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.progress_label = ttk.Label(action_frame, text="")
        self.progress_label.pack(side=tk.LEFT)

    # ─── RSS Feed Tab ───────────────────────────────────────────

    def _build_rss_tab(self):
        tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab, text="RSS Feed")

        # URL entry
        url_frame = ttk.Frame(tab)
        url_frame.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(url_frame, text="RSS URL:").pack(side=tk.LEFT)
        self.rss_url_var = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.rss_url_var, width=50).pack(side=tk.LEFT, padx=(4, 8), fill=tk.X, expand=True)
        ttk.Button(url_frame, text="Paste & Fetch", command=self._paste_and_fetch).pack(side=tk.LEFT)
        self.rss_fetch_btn = ttk.Button(url_frame, text="Fetch", command=self._fetch_rss)
        self.rss_fetch_btn.pack(side=tk.LEFT, padx=(4, 0))

        # Feed entries list with checkboxes
        entries_frame = ttk.LabelFrame(tab, text="Feed Entries", padding=8)
        entries_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        # Canvas + scrollbar for checkboxes
        canvas_frame = ttk.Frame(entries_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.rss_canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        rss_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.rss_canvas.yview)
        self.rss_canvas.configure(yscrollcommand=rss_scrollbar.set)

        self.rss_inner_frame = ttk.Frame(self.rss_canvas)
        self.rss_canvas_window = self.rss_canvas.create_window((0, 0), window=self.rss_inner_frame, anchor=tk.NW)

        self.rss_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rss_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.rss_inner_frame.bind("<Configure>", lambda e: self.rss_canvas.configure(scrollregion=self.rss_canvas.bbox("all")))
        self.rss_canvas.bind("<Configure>", lambda e: self.rss_canvas.itemconfig(self.rss_canvas_window, width=e.width))

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            self.rss_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.rss_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Select all / deselect all
        sel_row = ttk.Frame(entries_frame)
        sel_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(sel_row, text="Select All", command=self._rss_select_all).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(sel_row, text="Deselect All", command=self._rss_deselect_all).pack(side=tk.LEFT)
        self.rss_count_label = ttk.Label(sel_row, text="")
        self.rss_count_label.pack(side=tk.LEFT, padx=12)

        # Destination (no presets)
        dest_frame = ttk.LabelFrame(tab, text="Destination", padding=8)
        dest_frame.pack(fill=tk.X, pady=4)

        cat_row = ttk.Frame(dest_frame)
        cat_row.pack(fill=tk.X, pady=2)
        ttk.Label(cat_row, text="Category:").pack(side=tk.LEFT)
        self.rss_category_var = tk.StringVar()
        self.rss_category_combo = ttk.Combobox(cat_row, textvariable=self.rss_category_var, width=30)
        self.rss_category_combo.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Button(cat_row, text="Refresh", command=self._refresh_categories).pack(side=tk.LEFT)
        self.rss_category_combo.bind("<<ComboboxSelected>>", self._on_rss_category_selected)

        path_row = ttk.Frame(dest_frame)
        path_row.pack(fill=tk.X, pady=2)
        ttk.Label(path_row, text="Save Path:").pack(side=tk.LEFT)
        self.rss_savepath_var = tk.StringVar()
        ttk.Entry(path_row, textvariable=self.rss_savepath_var, width=40, state="readonly").pack(side=tk.LEFT, padx=(4, 8), fill=tk.X, expand=True)
        ttk.Button(path_row, text="Browse", command=self._rss_browse_savepath).pack(side=tk.LEFT)

        folder_row = ttk.Frame(dest_frame)
        folder_row.pack(fill=tk.X, pady=2)
        ttk.Label(folder_row, text="Folder Name:").pack(side=tk.LEFT)
        self.rss_folder_var = tk.StringVar()
        self.rss_folder_var.trace_add("write", lambda *_: self._rebuild_rss_savepath())
        ttk.Entry(folder_row, textvariable=self.rss_folder_var, width=40).pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        # Action bar
        rss_action = ttk.Frame(tab, padding=(0, 8))
        rss_action.pack(fill=tk.X)

        self.rss_start_btn = ttk.Button(rss_action, text="Download & Load", command=self._start_rss_loading)
        self.rss_start_btn.pack(side=tk.LEFT)
        self.rss_cancel_btn = ttk.Button(rss_action, text="Cancel", command=self._cancel_rss_loading, state=tk.DISABLED)
        self.rss_cancel_btn.pack(side=tk.LEFT, padx=8)

        self.rss_progress_var = tk.DoubleVar()
        self.rss_progress_bar = ttk.Progressbar(rss_action, variable=self.rss_progress_var, maximum=100)
        self.rss_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.rss_progress_label = ttk.Label(rss_action, text="")
        self.rss_progress_label.pack(side=tk.LEFT)

    # ═══════════════════════════════════════════════════════════════
    # Config ↔ UI
    # ═══════════════════════════════════════════════════════════════

    def _load_config_to_ui(self):
        conn = cfg.get_connection(self.config)
        self.host_var.set(conn["host"])
        self.port_var.set(str(conn["port"]))
        self.user_var.set(conn["username"])
        self.pass_var.set(conn["password"])

        opts = cfg.get_options(self.config)
        self.delay_var.set(str(opts["delay"]))
        self.paused_var.set(opts["paused_mode"])
        self.batch_var.set(str(opts["batch_size"]))

        self._refresh_preset_list()

        # Restore last RSS category
        last_rss_cat = self.config.get("last_used", {}).get("rss_category", "")
        if last_rss_cat:
            self.rss_category_var.set(last_rss_cat)

    def _save_options(self):
        """Save the Options section (delay, paused mode, batch size) to config immediately."""
        self._save_ui_to_config()
        self._log("Options saved.", "info")

    def _save_ui_to_config(self):
        self.config = cfg.set_connection(
            self.config, self.host_var.get(), self.port_var.get(),
            self.user_var.get(), self.pass_var.get(),
        )
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            delay = 1.0
        try:
            batch = int(self.batch_var.get())
        except ValueError:
            batch = 5
        self.config = cfg.set_options(self.config, delay, self.paused_var.get(), batch)

    # ═══════════════════════════════════════════════════════════════
    # Connection (shared)
    # ═══════════════════════════════════════════════════════════════

    def _test_connection(self):
        self._save_ui_to_config()
        conn = cfg.get_connection(self.config)
        self.test_btn.configure(state=tk.DISABLED)
        self.conn_status.configure(text="Connecting...", foreground="gray")

        def _worker():
            client = QBitClient(conn["host"], conn["port"], conn["username"], conn["password"])
            ok, msg = client.test_connection()
            cats = client.get_categories() if ok else []
            cat_details = client.get_category_details() if ok else {}

            def _update():
                self.test_btn.configure(state=tk.NORMAL)
                if ok:
                    self.qbit = client
                    self.category_paths = cat_details
                    self.conn_status.configure(text=msg, foreground="#2e7d32")
                    self.category_combo["values"] = cats
                    self.rss_category_combo["values"] = cats
                else:
                    self.qbit = None
                    self.category_paths = {}
                    self.conn_status.configure(text=msg, foreground="#c62828")

            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    def _refresh_categories(self):
        """Refresh category dropdowns from qBittorrent without a full connection test."""
        if not self.qbit:
            messagebox.showinfo("Not Connected", "Connect to qBittorrent first (press Test).")
            return

        def _worker():
            cats = self.qbit.get_categories()
            details = self.qbit.get_category_details()

            def _update():
                self.category_paths = details
                self.category_combo["values"] = cats
                self.rss_category_combo["values"] = cats

            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    # ═══════════════════════════════════════════════════════════════
    # File Loader Tab — Logic
    # ═══════════════════════════════════════════════════════════════

    def _set_files(self, file_list):
        self.selected_files = list(file_list)
        self.original_files = list(file_list)
        self.sort_var.set("Original Sequence")
        self._refresh_file_listbox()

    def _refresh_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for f in self.selected_files:
            self.file_listbox.insert(tk.END, os.path.basename(f))
        count = len(self.selected_files)
        if count == 0:
            text = "No files selected — browse or drag && drop" if HAS_DND else "No files selected"
        else:
            text = f"{count} file(s) selected"
        self.file_count_label.configure(text=text)

    def _remove_selected_files(self):
        indices = list(self.file_listbox.curselection())
        if not indices:
            return
        for i in reversed(indices):
            del self.selected_files[i]
        self._refresh_file_listbox()

    def _remove_all_files(self):
        self.selected_files = []
        self.original_files = []
        self._refresh_file_listbox()

    def _on_sort_changed(self, event=None):
        if self.sort_var.get() == "Alphabetically":
            self.selected_files = sorted(self.selected_files, key=lambda f: os.path.basename(f).lower())
        else:
            # Restore original order, keeping only files still in the current list
            remaining = set(self.selected_files)
            self.selected_files = [f for f in self.original_files if f in remaining]
        self._refresh_file_listbox()

    def _browse_files(self):
        initial_dir = self.config.get("last_used", {}).get("browse_dir", "")
        files = filedialog.askopenfilenames(
            title="Select .torrent files",
            initialdir=initial_dir or None,
            filetypes=[("Torrent files", "*.torrent"), ("All files", "*.*")],
        )
        if not files:
            return
        self.config.setdefault("last_used", {})["browse_dir"] = os.path.dirname(files[0])
        cfg.save_config(self.config)
        self._set_files(list(files))

    def _on_drop(self, event):
        raw = event.data
        paths = []
        i = 0
        while i < len(raw):
            if raw[i] == '{':
                end = raw.index('}', i)
                paths.append(raw[i + 1:end])
                i = end + 2
            elif raw[i] == ' ':
                i += 1
            else:
                end = raw.find(' ', i)
                if end == -1:
                    end = len(raw)
                paths.append(raw[i:end])
                i = end + 1
        torrent_files = [p for p in paths if p.lower().endswith('.torrent')]
        if torrent_files:
            self._set_files(torrent_files)

    def _browse_savepath(self):
        path = filedialog.askdirectory(title="Select save directory")
        if path:
            self.savepath_var.set(path)

    # Presets
    def _refresh_preset_list(self):
        presets = cfg.get_presets(self.config)
        names = list(presets.keys())
        self.preset_combo["values"] = names
        last = self.config.get("last_used", {}).get("preset", "")
        if last in names:
            self.preset_var.set(last)
            self._apply_preset(last)

    def _on_fl_category_selected(self, event=None):
        cat = self.category_var.get()
        path = self.category_paths.get(cat, "")
        if path:
            self.savepath_var.set(path)
        self.preset_var.set("")

    def _on_preset_selected(self, event=None):
        name = self.preset_var.get()
        if name:
            self._apply_preset(name)

    def _apply_preset(self, name):
        presets = cfg.get_presets(self.config)
        if name in presets:
            p = presets[name]
            self.category_var.set(p.get("category", ""))
            self.savepath_var.set(p.get("save_path", ""))
            self.config.setdefault("last_used", {})["preset"] = name
            cfg.save_config(self.config)

    def _save_preset(self):
        category = self.category_var.get().strip()
        save_path = self.savepath_var.get().strip()
        if not category and not save_path:
            messagebox.showwarning("Save Preset", "Enter a category and/or save path first.")
            return
        name = f"{category} - {save_path}" if category and save_path else category or save_path
        custom = simpledialog.askstring("Save Preset", "Preset name:", initialvalue=name, parent=self.root)
        if not custom:
            return
        self.config = cfg.add_preset(self.config, custom, category, save_path)
        self._refresh_preset_list()
        self.preset_var.set(custom)

    def _delete_preset(self):
        name = self.preset_var.get()
        if not name:
            return
        if messagebox.askyesno("Delete Preset", f"Delete preset '{name}'?"):
            self.config = cfg.delete_preset(self.config, name)
            self.preset_var.set("")
            self.category_var.set("")
            self.savepath_var.set("")
            self._refresh_preset_list()

    # File Loader batch
    def _start_loading(self):
        if not self.selected_files:
            messagebox.showwarning("No Files", "Select .torrent files first.")
            return
        if not self.qbit:
            messagebox.showwarning("Not Connected", "Test the connection to qBittorrent first.")
            return

        self._save_ui_to_config()
        self.cancel_event.clear()
        self.loading = True
        self.start_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self._clear_log()
        self.progress_var.set(0)

        category = self.category_var.get().strip()
        save_path = self.savepath_var.get().strip()
        delay = float(self.delay_var.get() or "1.0")
        paused_mode = self.paused_var.get()
        batch_size = int(self.batch_var.get() or "5")

        worker = threading.Thread(
            target=self._loading_worker,
            args=(list(self.selected_files), category, save_path, delay, paused_mode, batch_size),
            daemon=True,
        )
        worker.start()

    def _loading_worker(self, files, category, save_path, delay, paused_mode, batch_size):
        total = len(files)
        added = skipped = errors = 0
        self._log(f"Loading {total} torrent(s)...", "info")

        for i, filepath in enumerate(files):
            if self.cancel_event.is_set():
                self._log("Cancelled by user.", "error")
                break

            name = os.path.basename(filepath)
            status, msg = self.qbit.add_torrent(filepath, category, save_path, paused=paused_mode)

            if status == "ok":
                self._log(f"  + {name}", "ok")
                added += 1
            elif status == "skip":
                self._log(f"  ~ {name} — {msg}", "skip")
                skipped += 1
            else:
                self._log(f"  x {name} — {msg}", "error")
                errors += 1

            progress = ((i + 1) / total) * 100
            self.root.after(0, lambda p=progress, c=i+1, t=total: self._update_progress(p, c, t))

            if i < total - 1 and not self.cancel_event.is_set():
                time.sleep(delay)

        if paused_mode and added > 0 and not self.cancel_event.is_set():
            self._log("", "info")
            self._log("Resuming torrents in batches...", "info")
            hashes = self.qbit.get_paused_torrents(category)
            for bs in range(0, len(hashes), batch_size):
                if self.cancel_event.is_set():
                    break
                batch = hashes[bs:bs + batch_size]
                ok, msg = self.qbit.resume_torrents(batch)
                if ok:
                    self._log(f"  Resumed batch {bs // batch_size + 1} ({len(batch)} torrents)", "ok")
                else:
                    self._log(f"  Resume failed: {msg}", "error")
                if bs + batch_size < len(hashes):
                    time.sleep(delay)

        self._log("", "info")
        self._log(f"Done — Added: {added}  Skipped: {skipped}  Errors: {errors}", "info")
        self.root.after(0, self._loading_finished)

    def _update_progress(self, percent, current, total):
        self.progress_var.set(percent)
        self.progress_label.configure(text=f"{current}/{total}")

    def _loading_finished(self):
        self.loading = False
        self.start_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)

    def _cancel_loading(self):
        self.cancel_event.set()

    # ═══════════════════════════════════════════════════════════════
    # RSS Feed Tab — Logic
    # ═══════════════════════════════════════════════════════════════

    def _paste_and_fetch(self):
        """Paste clipboard contents into the URL field and fetch immediately."""
        try:
            clipboard = self.root.clipboard_get()
        except tk.TclError:
            return
        self.rss_url_var.set(clipboard.strip())
        self._fetch_rss()

    def _fetch_rss(self):
        url = self.rss_url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Paste an RSS feed URL first.")
            return

        self.rss_fetch_btn.configure(state=tk.DISABLED)
        self._log("Fetching RSS feed...", "info")

        def _worker():
            ok, result = fetch_feed(url)

            def _update():
                self.rss_fetch_btn.configure(state=tk.NORMAL)
                if ok:
                    self.rss_entries = sorted(result, key=lambda e: e["title"])
                    self._populate_rss_entries()
                    # Smart name suggestion
                    titles = [e["title"] for e in result]
                    self.rss_smart_name = extract_smart_name(titles)
                    self._update_rss_savepath()
                    self._log(f"Found {len(result)} entries in feed.", "ok")
                else:
                    self._log(f"RSS error: {result}", "error")

            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    def _populate_rss_entries(self):
        # Clear existing
        for widget in self.rss_inner_frame.winfo_children():
            widget.destroy()
        self.rss_check_vars.clear()

        for i, entry in enumerate(self.rss_entries):
            var = tk.BooleanVar(value=True)
            self.rss_check_vars.append(var)

            row = ttk.Frame(self.rss_inner_frame)
            row.pack(fill=tk.X, pady=1)

            cb = ttk.Checkbutton(row, variable=var, command=self._update_rss_count)
            cb.pack(side=tk.LEFT)

            title_label = ttk.Label(row, text=entry["title"], wraplength=400, anchor=tk.W)
            title_label.pack(side=tk.LEFT, padx=(4, 8), fill=tk.X, expand=True)

            if entry["size"]:
                size_label = ttk.Label(row, text=entry["size"], foreground="gray", width=12, anchor=tk.E)
                size_label.pack(side=tk.RIGHT)

        self._update_rss_count()

    def _update_rss_count(self):
        checked = sum(1 for v in self.rss_check_vars if v.get())
        total = len(self.rss_check_vars)
        self.rss_count_label.configure(text=f"{checked}/{total} selected")

    def _rss_select_all(self):
        for v in self.rss_check_vars:
            v.set(True)
        self._update_rss_count()

    def _rss_deselect_all(self):
        for v in self.rss_check_vars:
            v.set(False)
        self._update_rss_count()

    def _on_rss_category_selected(self, event=None):
        # Remember last picked category
        self.config.setdefault("last_used", {})["rss_category"] = self.rss_category_var.get()
        cfg.save_config(self.config)
        self._update_rss_savepath()

    def _update_rss_savepath(self):
        """Set folder name from smart name, which triggers save path rebuild."""
        if self.rss_smart_name:
            self.rss_folder_var.set(self.rss_smart_name)
        # If no smart name, just rebuild with whatever's in the folder field
        self._rebuild_rss_savepath()

    def _rebuild_rss_savepath(self):
        """Reconstruct full save path from category base + folder name."""
        cat = self.rss_category_var.get().strip()
        base = self.category_paths.get(cat, "")
        folder = self.rss_folder_var.get().strip()

        if base and folder:
            full = os.path.join(base, folder)
        elif base:
            full = base
        elif folder:
            full = folder
        else:
            full = ""

        self.rss_savepath_var.set(full)

    def _rss_browse_savepath(self):
        path = filedialog.askdirectory(title="Select base directory")
        if path:
            # Use browsed path as base, keep folder name appended
            folder = self.rss_folder_var.get().strip()
            if folder:
                self.rss_savepath_var.set(os.path.join(path, folder))
            else:
                self.rss_savepath_var.set(path)

    def _start_rss_loading(self):
        if not self.rss_entries:
            messagebox.showwarning("No Entries", "Fetch an RSS feed first.")
            return
        if not self.qbit:
            messagebox.showwarning("Not Connected", "Test the connection to qBittorrent first.")
            return

        selected = [(e, v) for e, v in zip(self.rss_entries, self.rss_check_vars) if v.get()]
        if not selected:
            messagebox.showwarning("None Selected", "Select at least one entry to download.")
            return

        self._save_ui_to_config()
        self.rss_cancel_event.clear()
        self.rss_start_btn.configure(state=tk.DISABLED)
        self.rss_cancel_btn.configure(state=tk.NORMAL)
        self._clear_log()
        self.rss_progress_var.set(0)

        entries = [e for e, _ in selected]
        category = self.rss_category_var.get().strip()
        save_path = self.rss_savepath_var.get().strip()
        delay = float(self.delay_var.get() or "1.0")

        worker = threading.Thread(
            target=self._rss_loading_worker,
            args=(entries, category, save_path, delay),
            daemon=True,
        )
        worker.start()

    def _rss_loading_worker(self, entries, category, save_path, delay):
        total = len(entries)
        added = skipped = errors = 0
        temp_dir = tempfile.mkdtemp(prefix="mtl_rss_")

        self._log(f"Downloading & loading {total} torrent(s) from RSS...", "info")

        for i, entry in enumerate(entries):
            if self.rss_cancel_event.is_set():
                self._log("Cancelled by user.", "error")
                break

            title = entry["title"]

            # Download .torrent file
            ok, result = download_torrent(entry["download_url"], temp_dir)
            if not ok:
                self._log(f"  x {title} — {result}", "error")
                errors += 1
            else:
                # Add to qBittorrent
                status, msg = self.qbit.add_torrent(result, category, save_path)
                if status == "ok":
                    self._log(f"  + {title}", "ok")
                    added += 1
                elif status == "skip":
                    self._log(f"  ~ {title} — {msg}", "skip")
                    skipped += 1
                else:
                    self._log(f"  x {title} — {msg}", "error")
                    errors += 1

            progress = ((i + 1) / total) * 100
            self.root.after(0, lambda p=progress, c=i+1, t=total: self._rss_update_progress(p, c, t))

            if i < total - 1 and not self.rss_cancel_event.is_set():
                time.sleep(delay)

        # Cleanup temp files
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        self._log("", "info")
        self._log(f"Done — Added: {added}  Skipped: {skipped}  Errors: {errors}", "info")
        self.root.after(0, self._rss_loading_finished)

    def _rss_update_progress(self, percent, current, total):
        self.rss_progress_var.set(percent)
        self.rss_progress_label.configure(text=f"{current}/{total}")

    def _rss_loading_finished(self):
        self.rss_start_btn.configure(state=tk.NORMAL)
        self.rss_cancel_btn.configure(state=tk.DISABLED)

    def _cancel_rss_loading(self):
        self.rss_cancel_event.set()

    # ═══════════════════════════════════════════════════════════════
    # Shared Logging
    # ═══════════════════════════════════════════════════════════════

    def _log(self, message, tag="info"):
        def _append():
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n", tag)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.root.after(0, _append)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main():
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = MassTorrentLoader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
