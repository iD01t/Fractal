import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
import customtkinter as ctk  # pip install customtkinter
import numpy as np
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageOps
import threading
import time  # For debounce
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
import math

# --- OPTIONAL IMPORTS & CONFIG ---
try:
    from scipy.ndimage import map_coordinates
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

ctk.set_appearance_mode("dark")  # Modes: "system" (default), "light", "dark"
ctk.set_default_color_theme("dark-blue")  # Themes: "blue", "dark-blue", "green"

# --- CONSTANTS & CONFIG ---
APP_NAME = "Fractal Dream Weaver Pro"
VERSION = "1.0"
AUTHOR = "Guillaume Lessard"
COPYRIGHT_YEAR = "2025"
CONTACT_EMAIL = "admin@id01t.store"
LICENSE_INFO = "Licensed to end user under EULA."

# --- LOGGING SETUP ---
def setup_logging():
    """Configures a rotating file logger for the application."""
    logger = logging.getLogger(APP_NAME)
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.INFO)

    log_dir = ""
    # Determine log directory based on execution mode (frozen exe vs. script)
    if getattr(sys, 'frozen', False):
        log_dir = os.path.dirname(sys.executable)
    else:
        log_dir = os.path.dirname(os.path.abspath(__file__))

    log_file = os.path.join(log_dir, "fractal_dream_weaver.log")

    # Use a rotating file handler to prevent log files from growing indefinitely
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=2) # 5MB file size limit
    handler.setFormatter(log_formatter)
    logger.addHandler(handler)

    # Also log unhandled exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    return logger


class FractalDreamWeaver:
    def __init__(self, root, logger):
        self.root = root
        self.logger = logger
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("1400x900")
        self.root.resizable(True, True)
        
        # Default parameters (expanded)
        self.width = tk.IntVar(value=800)
        self.height = tk.IntVar(value=600)
        self.zoom = tk.DoubleVar(value=1.0)
        self.center_x = tk.DoubleVar(value=0.0)
        self.center_y = tk.DoubleVar(value=0.0)
        self.max_iter = tk.IntVar(value=256)
        self.power = tk.DoubleVar(value=2.0)  # New: For Multibrot-like
        self.c_real = tk.DoubleVar(value=-0.7)
        self.c_imag = tk.DoubleVar(value=0.27)
        self.fractal_type = tk.StringVar(value="Mandelbrot")
        self.landscape_type = tk.StringVar(value="Dream")
        self.nightmare_mode = tk.BooleanVar(value=False)
        self.weave_mode = tk.BooleanVar(value=True)
        self.brush_size = tk.IntVar(value=5)
        self.brush_color = (255, 255, 255, 128)  # Semi-transparent white for dark mode
        self.filter_type = tk.StringVar(value="None")
        self.auto_update = tk.BooleanVar(value=False)  # New: Auto-generate on change
        self.invert_colors = tk.BooleanVar(value=False)  # New: Color inversion
        self.num_frames = tk.IntVar(value=20)  # For animation
        self.frame_duration = tk.IntVar(value=100)  # ms
        self.appearance_mode = tk.StringVar(value="dark")  # For toggle
        
        # Sketch image for weaving
        self.sketch_img = Image.new('RGBA', (self.width.get(), self.height.get()), (255, 255, 255, 0))
        self.sketch_draw = ImageDraw.Draw(self.sketch_img)  # Renamed to avoid conflict
        self.last_pos = None
        
        # Debounce for drawing
        self.debounce_id = None
        self.debounce_delay = 500  # ms
        
        # Status
        self.status_text = tk.StringVar(value="Ready")

        # Panning state (for realtime exploration)
        self.panning = False  # True when user is panning instead of drawing
        self.pan_start_px = 0
        self.pan_start_py = 0
        self.pan_center_x = 0.0
        self.pan_center_y = 0.0
        self.last_pan_time = time.time()
        
        # UI Setup with CustomTkinter for pro look
        self.setup_ui()
        
        # Bind resize to update preview
        self.root.bind("<Configure>", self.on_resize)
        
        # Generate initial fractal in thread
        self.logger.info(f"--- {APP_NAME} v{VERSION} Started ---")
        if not SCIPY_AVAILABLE:
            self.logger.warning("SciPy not found. The 'Swirl' filter will use a lower-quality NumPy implementation.")

        self.thread_generate()

    def setup_ui(self):
        """Creates and organizes the entire user interface."""
        # Main frame
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Notebook for tabs
        notebook = ctk.CTkTabview(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        preview_tab = notebook.add("Preview")
        param_tab = notebook.add("Parameters")

        # --- Preview Tab ---
        self.preview_frame = ctk.CTkFrame(preview_tab, fg_color="black")
        self.preview_frame.pack(fill=tk.BOTH, expand=True)
        self.preview_label = ctk.CTkLabel(self.preview_frame, text="")
        self.preview_label.pack(fill=tk.BOTH, expand=True)
        self.preview_label.bind("<Button-1>", self.on_mouse_down)
        self.preview_label.bind("<B1-Motion>", self.on_mouse_drag)
        self.preview_label.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.preview_label.bind("<MouseWheel>", self.on_mouse_wheel)
        self.root.bind("<Configure>", self.on_resize)

        # Status Bar & Progress Bar
        status_frame = ctk.CTkFrame(preview_tab)
        status_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        self.progressbar = ctk.CTkProgressBar(status_frame, orientation="horizontal", mode="indeterminate")
        self.progressbar.pack(side=tk.RIGHT, padx=(10, 5), pady=5)
        self.status_label = ctk.CTkLabel(status_frame, textvariable=self.status_text, anchor="w")
        self.status_label.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)

        # --- Parameters Tab ---
        param_frame = ctk.CTkScrollableFrame(param_tab)
        param_frame.pack(fill=tk.BOTH, expand=True)

        # -- Fractal Settings --
        fractal_section = self._create_section_header(param_frame, "Fractal Settings")
        self._create_entry_with_label(fractal_section, "Width", self.width)
        self._create_entry_with_label(fractal_section, "Height", self.height)
        self._create_slider_with_label(fractal_section, "Zoom", self.zoom, 0.1, 10000.0)
        self._create_slider_with_label(fractal_section, "Center X", self.center_x, -2.5, 2.5)
        self._create_slider_with_label(fractal_section, "Center Y", self.center_y, -2.0, 2.0)
        self._create_slider_with_label(fractal_section, "Max Iterations", self.max_iter, 50, 2000, "int")
        self._create_slider_with_label(fractal_section, "Power", self.power, 0.5, 8.0)
        ctk.CTkLabel(fractal_section, text="Fractal Type").pack(fill=tk.X, padx=5, pady=(10,0))
        ctk.CTkOptionMenu(fractal_section, variable=self.fractal_type, values=["Mandelbrot", "Julia", "Burning Ship", "Tricorn"], command=self._on_fractal_type_change).pack(fill=tk.X, padx=5, pady=5)

        # -- Julia Parameters (conditionally enabled) --
        self.julia_section = self._create_section_header(param_frame, "Julia Parameters")
        self.c_real_slider = self._create_slider_with_label(self.julia_section, "C Real", self.c_real, -2.0, 2.0)
        self.c_imag_slider = self._create_slider_with_label(self.julia_section, "C Imag", self.c_imag, -2.0, 2.0)
        
        # -- Landscape & Palette --
        landscape_section = self._create_section_header(param_frame, "Landscape & Palette")
        landscape_options = ["Forest", "City", "Dream", "Ocean", "Desert", "Space", "Rainbow", "Fire", "Ice", "Inferno"]
        ctk.CTkLabel(landscape_section, text="Palette").pack(fill=tk.X, padx=5)
        ctk.CTkOptionMenu(landscape_section, variable=self.landscape_type, values=landscape_options, command=self.param_changed).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkCheckBox(landscape_section, text="Nightmare Mode", variable=self.nightmare_mode, command=self.param_changed).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkCheckBox(landscape_section, text="Invert Colors", variable=self.invert_colors, command=self.param_changed).pack(fill=tk.X, padx=5, pady=5)

        # -- Filters --
        filter_section = self._create_section_header(param_frame, "Filters")
        filter_options = ["None", "Blur", "Edge", "Emboss", "Sharpen", "Contour", "Swirl"]
        ctk.CTkLabel(filter_section, text="Apply Filter").pack(fill=tk.X, padx=5)
        ctk.CTkOptionMenu(filter_section, variable=self.filter_type, values=filter_options, command=self.param_changed).pack(fill=tk.X, padx=5, pady=5)

        # -- Weave & Draw --
        weave_section = self._create_section_header(param_frame, "Weave & Draw")
        ctk.CTkCheckBox(weave_section, text="Weave Mode", variable=self.weave_mode, command=self.param_changed).pack(fill=tk.X, padx=5, pady=5)
        self._create_slider_with_label(weave_section, "Brush Size", self.brush_size, 1, 50, "int")
        ctk.CTkButton(weave_section, text="Brush Color", command=self.choose_brush_color).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(weave_section, text="Clear Sketch", command=self.clear_sketch).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(weave_section, text="Load Background", command=self.load_background).pack(fill=tk.X, padx=5, pady=5)

        # -- Animation --
        anim_section = self._create_section_header(param_frame, "Animation")
        self._create_entry_with_label(anim_section, "Frames", self.num_frames)
        self._create_entry_with_label(anim_section, "Duration (ms)", self.frame_duration)
        feature/fractal-dream-weaver-pro
        
        # -- Presets --
        preset_section = self._create_section_header(param_frame, "Presets")
        ctk.CTkButton(preset_section, text="Spiral Galaxy (Julia)", command=self.load_preset_spiral).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(preset_section, text="Seahorse Valley (Mandelbrot)", command=self.load_preset_seahorse).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(preset_section, text="Cosmic Reef (Burning Ship)", command=self.load_preset_cosmic_reef).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(preset_section, text="Dragon's Breath (Tricorn)", command=self.load_preset_dragons_breath).pack(fill=tk.X, padx=5, pady=5)

        # -- Controls & Application --
        controls_section = self._create_section_header(param_frame, "Controls & Application")
        ctk.CTkCheckBox(controls_section, text="Auto Update on Change", variable=self.auto_update).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(controls_section, text="Generate", command=self.thread_generate).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(controls_section, text="Export Image", command=self.export_image).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(controls_section, text="Export Animation", command=self.thread_animate).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkLabel(controls_section, text="Appearance Mode").pack(fill=tk.X, padx=5, pady=(10,0))
        ctk.CTkOptionMenu(controls_section, variable=self.appearance_mode, values=["light", "dark", "system"], command=self.change_appearance).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(controls_section, text="About", command=self.show_about).pack(fill=tk.X, padx=5, pady=5)

        # Final setup
        self._on_fractal_type_change(self.fractal_type.get())

    def _create_section_header(self, parent, text):
        section_frame = ctk.CTkFrame(parent, fg_color=("gray90", "gray20"))
        section_frame.pack(fill=tk.X, pady=(10, 2), padx=5, ipady=3)
        ctk.CTkLabel(section_frame, text=text, font=ctk.CTkFont(weight="bold")).pack()
        return ctk.CTkFrame(parent) # Return a content frame
        
    def _create_slider_with_label(self, parent, text, variable, from_, to, var_type="float"):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill=tk.X, padx=5, pady=(2,2))
        
        label = ctk.CTkLabel(frame, text=text, width=120)
        label.pack(side=tk.LEFT, padx=(5, 10))
        
        value_label = ctk.CTkLabel(frame, text="", width=50, anchor="e")
        value_label.pack(side=tk.RIGHT, padx=(10, 5))

        def update_from_slider(value):
            if var_type == "int":
                value_label.configure(text=f"{int(float(value))}")
            else:
                value_label.configure(text=f"{float(value):.3f}")
            if self.auto_update.get():
                self.trigger_generation()
        
        def update_from_var(*args):
            val = variable.get()
            if var_type == "int":
                value_label.configure(text=f"{int(val)}")
                slider.set(int(val))
            else:
                value_label.configure(text=f"{float(val):.3f}")
                slider.set(float(val))

        number_of_steps = (to - from_) if var_type == "int" else None
        slider = ctk.CTkSlider(frame, variable=variable, from_=from_, to=to, number_of_steps=number_of_steps, command=update_from_slider)
        slider.pack(fill=tk.X, expand=True)
        
        variable.trace_add("write", update_from_var)
        update_from_var() # Initial set
        return slider

    def _create_entry_with_label(self, parent, text, variable):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill=tk.X, padx=5, pady=(2,2))
        label = ctk.CTkLabel(frame, text=text, width=120)
        label.pack(side=tk.LEFT, padx=(5, 10))
        entry = ctk.CTkEntry(frame, textvariable=variable)
        entry.pack(fill=tk.X, expand=True, padx=(0, 5))
        return entry

    def _on_fractal_type_change(self, fractal_type):
        """Conditionally enables or disables the Julia parameter controls."""
        is_julia = (fractal_type == "Julia")
        new_state = tk.NORMAL if is_julia else tk.DISABLED
        
        # The self.julia_section frame contains rows (which are also frames).
        # We need to iterate through the widgets inside each row.
        for row_frame in self.julia_section.winfo_children():
            for widget in row_frame.winfo_children():
                # Only CTkSlider widgets can be disabled.
                if isinstance(widget, ctk.CTkSlider):
                    widget.configure(state=new_state)
        

        
        # -- Presets --
        preset_section = self._create_section_header(param_frame, "Presets")
        ctk.CTkButton(preset_section, text="Spiral Galaxy (Julia)", command=self.load_preset_spiral).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(preset_section, text="Seahorse Valley (Mandelbrot)", command=self.load_preset_seahorse).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(preset_section, text="Cosmic Reef (Burning Ship)", command=self.load_preset_cosmic_reef).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(preset_section, text="Dragon's Breath (Tricorn)", command=self.load_preset_dragons_breath).pack(fill=tk.X, padx=5, pady=5)

        # -- Controls & Application --
        controls_section = self._create_section_header(param_frame, "Controls & Application")
        ctk.CTkCheckBox(controls_section, text="Auto Update on Change", variable=self.auto_update).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(controls_section, text="Generate", command=self.thread_generate).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(controls_section, text="Export Image", command=self.export_image).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(controls_section, text="Export Animation", command=self.thread_animate).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkLabel(controls_section, text="Appearance Mode").pack(fill=tk.X, padx=5, pady=(10,0))
        ctk.CTkOptionMenu(controls_section, variable=self.appearance_mode, values=["light", "dark", "system"], command=self.change_appearance).pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(controls_section, text="About", command=self.show_about).pack(fill=tk.X, padx=5, pady=5)

        # Final setup
        self._on_fractal_type_change(self.fractal_type.get())

    def _create_section_header(self, parent, text):
        section_frame = ctk.CTkFrame(parent, fg_color=("gray90", "gray20"))
        section_frame.pack(fill=tk.X, pady=(10, 2), padx=5, ipady=3)
        ctk.CTkLabel(section_frame, text=text, font=ctk.CTkFont(weight="bold")).pack()
        return ctk.CTkFrame(parent) # Return a content frame
        
    def _create_slider_with_label(self, parent, text, variable, from_, to, var_type="float"):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill=tk.X, padx=5, pady=(2,2))
        
        label = ctk.CTkLabel(frame, text=text, width=120)
        label.pack(side=tk.LEFT, padx=(5, 10))
        
        value_label = ctk.CTkLabel(frame, text="", width=50, anchor="e")
        value_label.pack(side=tk.RIGHT, padx=(10, 5))

        def update_from_slider(value):
            if var_type == "int":
                value_label.configure(text=f"{int(float(value))}")
            else:
                value_label.configure(text=f"{float(value):.3f}")
            if self.auto_update.get():
                self.trigger_generation()
        
        def update_from_var(*args):
            val = variable.get()
            if var_type == "int":
                value_label.configure(text=f"{int(val)}")
                slider.set(int(val))
            else:
                value_label.configure(text=f"{float(val):.3f}")
                slider.set(float(val))

        number_of_steps = (to - from_) if var_type == "int" else None
        slider = ctk.CTkSlider(frame, variable=variable, from_=from_, to=to, number_of_steps=number_of_steps, command=update_from_slider)
        slider.pack(fill=tk.X, expand=True)
        
        variable.trace_add("write", update_from_var)
        update_from_var() # Initial set
        return slider

    def _create_entry_with_label(self, parent, text, variable):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill=tk.X, padx=5, pady=(2,2))
        label = ctk.CTkLabel(frame, text=text, width=120)
        label.pack(side=tk.LEFT, padx=(5, 10))
        entry = ctk.CTkEntry(frame, textvariable=variable)
        entry.pack(fill=tk.X, expand=True, padx=(0, 5))
        return entry

    def _on_fractal_type_change(self, fractal_type):
        is_julia = (fractal_type == "Julia")
        new_state = tk.NORMAL if is_julia else tk.DISABLED
        
        # This will disable all widgets inside the Julia section frame
        for child in self.julia_section.winfo_children():
            child.configure(state=new_state)

        main
        if self.auto_update.get():
            self.trigger_generation()

    def param_changed(self, value=None):
        """Generic handler for non-slider parameter changes."""
        if self.auto_update.get():
            self.trigger_generation()

    def trigger_generation(self):
        """Debounces generation requests to avoid flooding the thread pool."""
        if self.debounce_id:
            self.root.after_cancel(self.debounce_id)
        # Use a shorter delay for interactive changes
        self.debounce_id = self.root.after(100, self.thread_generate)

    def thread_generate(self):
        """Start fractal generation in a daemon thread."""
        t = threading.Thread(target=self.generate_fractal)
        # Mark as daemon so it doesn't block application close
        t.daemon = True
        t.start()

    def generate_fractal(self):
        # Set status and cursor, and start progress animation in the main thread
        def start_ui():
            self.status_text.set("Generating...")
            self.root.config(cursor="wait")
            # Kick off indeterminate progress bar
            if hasattr(self, 'progressbar'):
                self.progressbar.start()
        self.root.after(0, start_ui)
        start_time = time.time()
        try:
            try:
                w, h = self.width.get(), self.height.get()
            except tk.TclError:
                self.logger.error("Invalid non-integer value in width/height fields.")
                self.status_text.set("Error: Width and Height must be numbers.")
                return

            if w <= 0 or h <= 0:
                self.logger.warning(f"Invalid dimensions for generation ({w}x{h}). Aborting.")
                return

            self.logger.info(f"Generating fractal: {self.fractal_type.get()} ({w}x{h}), Zoom: {self.zoom.get():.2f}, Iter: {self.max_iter.get()}")
            # Resize sketch and background if resolution changed
            if self.sketch_img.size != (w, h):
                self.sketch_img = self.sketch_img.resize((w, h), Image.Resampling.LANCZOS)
                self.sketch_draw = ImageDraw.Draw(self.sketch_img)
            if hasattr(self, 'background_img') and self.background_img.size != (w, h):
                self.background_img = self.background_img.resize((w, h), Image.Resampling.LANCZOS)

            # Compute fractal map and color it
            iter_map = self._generate_fractal_map(w, h)
            colors = self._color_fractal(iter_map)
            img = Image.fromarray(colors, 'RGB')

            # Apply filter
            img = self._apply_filter(img)

            # Invert if enabled
            if self.invert_colors.get():
                img = ImageOps.invert(img.convert('RGB'))

            # --- Image Compositing ---
            # Create a final RGBA canvas
            final_img = Image.new('RGBA', img.size)

            # 1. Paste background if it exists
            if hasattr(self, 'background_img') and self.background_img:
                try:
                    bg = self.background_img.resize(img.size, Image.Resampling.LANCZOS)
                    final_img.paste(bg.convert('RGBA'), (0, 0))
                except Exception as bg_e:
                    self.logger.error(f"Failed to process background image: {bg_e}")

            # 2. Paste fractal on top of background
            final_img.paste(img.convert('RGBA'), (0, 0), img.convert('RGBA'))

            # 3. Paste sketch on top of everything
            if self.weave_mode.get() and self.sketch_img:
                final_img.paste(self.sketch_img, (0, 0), self.sketch_img)

            # Store final composited image
            self.current_img = final_img

            # Display resized to fit preview
            self.update_preview()
        except Exception as e:
            self.logger.error(f"Fractal generation failed: {e}", exc_info=True)
            # Show error message in the main thread
            self.root.after(0, lambda: messagebox.showerror("Generation Error", f"An error occurred during generation: {e}"))
        finally:
            end_time = time.time()
            self.logger.info(f"Generation finished in {end_time - start_time:.2f} seconds.")
            # Reset status, cursor, and stop progress bar in the main thread
            def finish_ui():
                self.status_text.set("Ready")
                self.root.config(cursor="")
                if hasattr(self, 'progressbar'):
                    self.progressbar.stop()
            self.root.after(0, finish_ui)

    def update_preview(self):
        if hasattr(self, 'current_img'):
            fw, fh = self.preview_frame.winfo_width(), self.preview_frame.winfo_height()
            if fw > 1 and fh > 1:  # Avoid zero size
                display_img = self.current_img.resize((fw, fh), Image.Resampling.LANCZOS)
                ctk_photo = ctk.CTkImage(light_image=display_img, dark_image=display_img)
                self.preview_label.configure(image=ctk_photo)
                self.preview_label.image = ctk_photo

    # ---------- Interaction Handlers ----------
    def on_mouse_down(self, event):
        if self.weave_mode.get():
            self.start_draw(event)
        else:
            self.panning = True
            self.pan_start_px = event.x
            self.pan_start_py = event.y
            # For smooth panning, we don't need the center coordinates here yet

    def on_mouse_drag(self, event):
        if self.weave_mode.get():
            self.draw_line(event)
        elif self.panning:
            if not self.current_img: return

            dx = event.x - self.pan_start_px
            dy = event.y - self.pan_start_py

            # Create a temporary image for the pan preview
            # This is much faster than re-generating the fractal
            preview_w = self.preview_frame.winfo_width()
            preview_h = self.preview_frame.winfo_height()

            # Create a new blank image to paste the panned preview onto
            panned_preview = Image.new('RGBA', (preview_w, preview_h))

            # Resize the hi-res image to the preview size for this operation
            resized_current = self.current_img.resize((preview_w, preview_h), Image.Resampling.LANCZOS)

            # Paste the resized image at the new offset
            panned_preview.paste(resized_current, (dx, dy))

            # Update the label with this temporary panned image
            ctk_photo = ctk.CTkImage(light_image=panned_preview, dark_image=panned_preview, size=(preview_w, preview_h))
            self.preview_label.configure(image=ctk_photo)
            self.preview_label.image = ctk_photo


    def on_mouse_up(self, event):
        if self.panning:
            self.panning = False
            dx_px = event.x - self.pan_start_px
            dy_px = event.y - self.pan_start_py

            # Now, calculate the new center based on the total pan distance
            zoom = self.zoom.get()
            # Correctly map pixel delta to fractal coordinate delta
            w, h = self.width.get(), self.height.get()
            aspect_ratio = h / w if w > 0 and h > 0 else 1.0
            frac_range_x = 5.0 / zoom
            frac_range_y = frac_range_x * aspect_ratio

            delta_x_frac = (dx_px / w) * frac_range_x
            delta_y_frac = (dy_px / h) * frac_range_y

            new_center_x = self.center_x.get() - delta_x_frac
            new_center_y = self.center_y.get() + delta_y_frac # Y is inverted in screen coords

            self.center_x.set(new_center_x)
            self.center_y.set(new_center_y)
            self.trigger_generation()

        if self.weave_mode.get():
            self.last_pos = None

    def on_mouse_wheel(self, event):
        if not self.current_img: return

        # --- Zoom to Cursor ---
        # 1. Get mouse position in preview
        x, y = event.x, event.y
        preview_w = self.preview_frame.winfo_width()
        preview_h = self.preview_frame.winfo_height()

        # 2. Convert mouse position to fractal coordinates
        zoom = self.zoom.get()
        center_x, center_y = self.center_x.get(), self.center_y.get()
        w, h = self.width.get(), self.height.get()
        aspect_ratio = h / w if w > 0 and h > 0 else 1.0

        # Calculate the fractal space covered by the view
        frac_w = 5.0 / zoom
        frac_h = frac_w * aspect_ratio

        # Coordinate of the top-left corner
        x_min = center_x - frac_w / 2
        y_max = center_y + frac_h / 2

        # Get the fractal coordinate under the mouse
        mouse_frac_x = x_min + (x / preview_w) * frac_w
        mouse_frac_y = y_max - (y / preview_h) * frac_h # Y is inverted

        # 3. Calculate new zoom
        if event.delta > 0:
            zoom_factor = 1.25
        else:
            zoom_factor = 1 / 1.25
        new_zoom = max(0.1, min(self.zoom.get() * zoom_factor, 100000))

        # 4. Calculate new center to keep mouse coordinate stationary
        new_center_x = mouse_frac_x + (center_x - mouse_frac_x) / zoom_factor
        new_center_y = mouse_frac_y + (center_y - mouse_frac_y) / zoom_factor

        self.zoom.set(new_zoom)
        self.center_x.set(new_center_x)
        self.center_y.set(new_center_y)
        self.trigger_generation()

    def choose_brush_color(self):
        """
        Open a color chooser dialog and set the brush color for weaving.
        Returns a (R, G, B) tuple along with the hex value. The alpha channel
        remains semi-transparent to ensure overlay visibility.
        """
        result = colorchooser.askcolor(title="Select Brush Color", initialcolor="#FFFFFF")
        if result and result[0] is not None:
            r, g, b = [int(c) for c in result[0]]
            # Keep alpha at current value (semi-transparent)
            a = self.brush_color[3] if isinstance(self.brush_color, tuple) and len(self.brush_color) == 4 else 128
            self.brush_color = (r, g, b, a)

    def _generate_fractal_map(self, width, height):
        zoom = self.zoom.get()
        center_x = self.center_x.get()
        center_y = self.center_y.get()
        max_iter = self.max_iter.get()
        power = self.power.get()
        fractal_type = self.fractal_type.get()
        c_real = self.c_real.get()
        c_imag = self.c_imag.get()
        
        # Correct aspect ratio handling
        aspect_ratio = height / width if width > 0 and height > 0 else 1.0
        x_range = 5.0 / zoom
        y_range = x_range * aspect_ratio

        x_min = center_x - x_range / 2
        x_max = center_x + x_range / 2
        y_min = center_y - y_range / 2
        y_max = center_y + y_range / 2
        
        x = np.linspace(x_min, x_max, width)
        y = np.linspace(y_min, y_max, height)
        xx, yy = np.meshgrid(x, y)
        
        if fractal_type in ["Mandelbrot", "Burning Ship", "Tricorn"]:
            c = xx + 1j * yy
            z = np.zeros_like(c)
        elif fractal_type == "Julia":
            z = xx + 1j * yy
            c = complex(c_real, c_imag) * np.ones_like(z)
        else:
            raise ValueError("Invalid fractal type")
        
        iter_map = np.full((height, width), max_iter, dtype=int)
        mask = np.ones((height, width), dtype=bool)
        
        for i in range(max_iter):
            if fractal_type == "Burning Ship":
                z = np.abs(z.real) + 1j * np.abs(z.imag)
            elif fractal_type == "Tricorn":
                z = np.conj(z)
            z = z**power + c
            diverged = np.abs(z) > 2
            iter_map[diverged & mask] = i
            mask[diverged] = False
            z[diverged] = 2  # Cap to prevent overflow
        
        return iter_map

    def _color_fractal(self, iter_map):
        max_iter = self.max_iter.get()
        normalized = iter_map / max_iter
        colors = np.zeros((iter_map.shape[0], iter_map.shape[1], 3), dtype=np.uint8)
        landscape = self.landscape_type.get()
        
        # Define color palettes for different themes
        if landscape == "Forest":
            levels = [0, 0.3, 0.6, 1.0]
            cmaps = np.array([[0, 0, 128], [34, 139, 34], [139, 69, 19], [255, 255, 255]])
        elif landscape == "City":
            levels = [0, 0.4, 0.7, 1.0]
            cmaps = np.array([[50, 50, 50], [100, 100, 100], [200, 0, 0], [255, 255, 255]])
        elif landscape == "Dream":
            levels = [0, 0.25, 0.5, 0.75, 1.0]
            cmaps = np.array([[255, 0, 0], [255, 165, 0], [255, 255, 0], [0, 128, 0], [0, 0, 255]])
        elif landscape == "Ocean":
            levels = [0, 0.3, 0.6, 1.0]
            cmaps = np.array([[0, 0, 50], [0, 100, 200], [100, 200, 255], [255, 255, 255]])
        elif landscape == "Desert":
            levels = [0, 0.3, 0.6, 1.0]
            cmaps = np.array([[200, 100, 0], [255, 200, 100], [255, 150, 50], [255, 255, 200]])
        elif landscape == "Space":
            levels = [0, 0.3, 0.6, 1.0]
            cmaps = np.array([[0, 0, 0], [50, 0, 100], [100, 0, 200], [200, 100, 255]])
        elif landscape == "Rainbow":
            # A vibrant rainbow palette based on ROYGBIV sequence
            levels = [0, 0.16, 0.33, 0.5, 0.66, 0.83, 1.0]
            cmaps = np.array([
                [255, 0, 0],      # Red
                [255, 165, 0],    # Orange
                [255, 255, 0],    # Yellow
                [0, 128, 0],      # Green
                [0, 0, 255],      # Blue
                [75, 0, 130],     # Indigo
                [148, 0, 211]     # Violet
            ])
        elif landscape == "Fire":
            # Fiery palette: dark reds to bright yellows
            levels = [0, 0.4, 0.8, 1.0]
            cmaps = np.array([
                [50, 0, 0],       # Dark red
                [200, 0, 0],      # Red
                [255, 140, 0],    # Orange
                [255, 255, 200]   # Light yellow
            ])
        elif landscape == "Ice":
            # Cool palette: deep blue to icy white
            levels = [0, 0.4, 0.8, 1.0]
            cmaps = np.array([
                [0, 0, 100],      # Deep blue
                [0, 100, 200],    # Blue
                [150, 200, 255],  # Light blue
                [255, 255, 255]   # White
            ])
        elif landscape == "Inferno":
            # Inferno palette inspired by Matplotlib's inferno colormap
            levels = [0, 0.25, 0.5, 0.75, 1.0]
            cmaps = np.array([
                [0, 0, 4],        # Dark purple
                [87, 15, 109],    # Purple
                [187, 55, 84],    # Magenta
                [249, 142, 50],   # Orange
                [255, 255, 85]    # Yellow
            ])
        
        for i in range(len(levels) - 1):
            mask = (normalized >= levels[i]) & (normalized < levels[i + 1])
            frac = (normalized[mask] - levels[i]) / (levels[i + 1] - levels[i])
            colors[mask] = cmaps[i] + frac[:, np.newaxis] * (cmaps[i + 1] - cmaps[i])
        
        if self.nightmare_mode.get():
            # Refined Nightmare Mode: tinted noise and organic spatial jitter
            # 1. Add tinted noise (more purples/blues)
            noise_r = np.random.randint(-20, 20, colors.shape[:2])
            noise_g = np.random.randint(-15, 15, colors.shape[:2])
            noise_b = np.random.randint(-30, 30, colors.shape[:2])

            colors[:,:,0] = np.clip(colors[:,:,0] + noise_r, 0, 255)
            colors[:,:,1] = np.clip(colors[:,:,1] + noise_g, 0, 255)
            colors[:,:,2] = np.clip(colors[:,:,2] + noise_b, 0, 255)

            # 2. Apply a weak, random swirl for spatial jitter
            h, w = colors.shape[:2]
            cx, cy = w / 2, h / 2
            yy, xx = np.mgrid[0:h, 0:w]
            r = np.sqrt((xx - cx)**2 + (yy - cy)**2)
            theta = np.arctan2(yy - cy, xx - cx)

            # Use random params for a unique jitter each time
            strength = np.random.uniform(0.1, 0.3)
            freq = np.random.uniform(8, 20)

            jitter_angle = strength * np.sin(r / (max(w, h) / freq))

            x_new = np.clip((cx + r * np.cos(theta + jitter_angle)), 0, w - 1).astype(int)
            y_new = np.clip((cy + r * np.sin(theta + jitter_angle)), 0, h - 1).astype(int)

            colors = colors[y_new, x_new]
        
        return colors

    def _apply_filter(self, img):
        filter_type = self.filter_type.get()
        if filter_type == "Blur":
            img = img.filter(ImageFilter.GaussianBlur(5))
        elif filter_type == "Edge":
            img = img.filter(ImageFilter.FIND_EDGES)
        elif filter_type == "Invert":
            img = ImageOps.invert(img)
        elif filter_type == "Swirl":
            self.logger.info(f"Applying Swirl filter. SciPy available: {SCIPY_AVAILABLE}")
            if SCIPY_AVAILABLE:
                strength = 2.0 if self.nightmare_mode.get() else 1.0
                arr = np.array(img)
                h, w = arr.shape[:2]
                cx, cy = w / 2, h / 2
                yy, xx = np.mgrid[0:h, 0:w]
                r = np.sqrt((xx - cx)**2 + (yy - cy)**2)
                theta = np.arctan2(yy - cy, xx - cx) + strength * np.exp(-r / (w / 5))
                x_new = cx + r * np.cos(theta)
                y_new = cy + r * np.sin(theta)
                for c in range(3):
                    arr[:, :, c] = map_coordinates(arr[:, :, c], [y_new, x_new], order=1, mode='nearest')
                img = Image.fromarray(arr)
            else:
                # Basic swirl using custom NumPy implementation
                self.logger.info("Using NumPy for Swirl effect.")
                return self._swirl_numpy(img)
        elif filter_type == "Emboss":
            img = img.filter(ImageFilter.EMBOSS)
        elif filter_type == "Sharpen":
            img = img.filter(ImageFilter.SHARPEN)
        elif filter_type == "Contour":
            img = img.filter(ImageFilter.CONTOUR)
        return img

    def _swirl_numpy(self, img):
        """
        A NumPy-based implementation of a swirl effect.
        Uses nearest-neighbor sampling for performance.
        """
        arr = np.array(img)
        h, w, c = arr.shape

        # Auto-downscale for performance on large images
        MAX_PIXELS = 2_000_000 # 2 megapixels
        if h * w > MAX_PIXELS:
            scale = math.sqrt(MAX_PIXELS / (h * w))
            new_h, new_w = int(h * scale), int(w * scale)
            self.logger.info(f"Image too large for numpy swirl, downscaling to {new_w}x{new_h}")
            small_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            swirled_small = self._swirl_numpy(small_img) # Recursive call on smaller image
            return swirled_small.resize((w, h), Image.Resampling.LANCZOS)

        cx, cy = w / 2, h / 2
        yy, xx = np.mgrid[0:h, 0:w]

        r = np.sqrt((xx - cx)**2 + (yy - cy)**2)
        theta = np.arctan2(yy - cy, xx - cx)

        strength = 2.0
        swirl_angle = strength * np.exp(-r / (max(w, h) / 5.0))

        x_new = (cx + r * np.cos(theta + swirl_angle)).astype(int)
        y_new = (cy + r * np.sin(theta + swirl_angle)).astype(int)

        x_new = np.clip(x_new, 0, w - 1)
        y_new = np.clip(y_new, 0, h - 1)

        swirled_arr = arr[y_new, x_new]
        return Image.fromarray(swirled_arr)

    def on_mouse_down(self, event):
        if self.weave_mode.get():
            self.last_draw_pos = (event.x, event.y)
        else:
            self.panning = True
            self.pan_start_px = event.x
            self.pan_start_py = event.y

    def on_mouse_drag(self, event):
        if self.weave_mode.get():
            if not self.last_draw_pos or not self.sketch_draw: return

            # Scale preview coordinates to full-resolution image coordinates
            w, h = self.width.get(), self.height.get()
            preview_w, preview_h = max(1, self.preview_frame.winfo_width()), max(1, self.preview_frame.winfo_height())
            scale_x, scale_y = w / preview_w, h / preview_h

            start_pos = (self.last_draw_pos[0] * scale_x, self.last_draw_pos[1] * scale_y)
            end_pos = (event.x * scale_x, event.y * scale_y)

            self.sketch_draw.line([start_pos, end_pos], fill=self.brush_color, width=self.brush_size.get(), joint="curve")
            self.last_draw_pos = (event.x, event.y)
            self.trigger_generation() # Redraw with the new line
        elif self.panning:
            # (rest of panning logic is unchanged)
            if not self.current_img: return

            dx = event.x - self.pan_start_px
            dy = event.y - self.pan_start_py

            preview_w = self.preview_frame.winfo_width()
            preview_h = self.preview_frame.winfo_height()
            panned_preview = Image.new('RGBA', (preview_w, preview_h))
            resized_current = self.current_img.resize((preview_w, preview_h), Image.Resampling.LANCZOS)
            panned_preview.paste(resized_current, (dx, dy))

            ctk_photo = ctk.CTkImage(light_image=panned_preview, dark_image=panned_preview, size=(preview_w, preview_h))
            self.preview_label.configure(image=ctk_photo)
            self.preview_label.image = ctk_photo

    def on_mouse_up(self, event):
        if self.panning:
            self.panning = False
            dx_px = event.x - self.pan_start_px
            dy_px = event.y - self.pan_start_py

            zoom = self.zoom.get()
            w, h = self.width.get(), self.height.get()
            aspect_ratio = h / w if w > 0 and h > 0 else 1.0
            frac_range_x = 5.0 / zoom
            frac_range_y = frac_range_x * aspect_ratio

            delta_x_frac = (dx_px / w) * frac_range_x
            delta_y_frac = (dy_px / h) * frac_range_y

            new_center_x = self.center_x.get() - delta_x_frac
            new_center_y = self.center_y.get() + delta_y_frac

            self.center_x.set(new_center_x)
            self.center_y.set(new_center_y)
            self.trigger_generation()

        if self.weave_mode.get():
            self.last_draw_pos = None

    def clear_sketch(self):
        w, h = self.width.get(), self.height.get()
        self.sketch_img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        self.sketch_draw = ImageDraw.Draw(self.sketch_img)
        self.trigger_generation()

    def load_background(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if path:
            try:
                self.background_img = Image.open(path)
                self.trigger_generation()
            except Exception as e:
                self.logger.error(f"Failed to load background image: {e}", exc_info=True)
                messagebox.showerror("Load Error", f"Could not load the background image.\n\nError: {e}")

    def load_preset_spiral(self):
        self.fractal_type.set("Julia")
        self.c_real.set(-0.8)
        self.c_imag.set(0.156)
        self.zoom.set(1.0)
        self.center_x.set(0.0)
        self.center_y.set(0.0)
        self.power.set(2.0)
        self.thread_generate()

    def load_preset_seahorse(self):
        self.fractal_type.set("Mandelbrot")
        self.zoom.set(100)
        self.center_x.set(-0.75)
        self.center_y.set(0.1)
        self.power.set(2.0)
        self.thread_generate()

    def load_preset_cosmic_reef(self):
        """Loads a preset for a 'Cosmic Reef' view in the Burning Ship fractal."""
        self.fractal_type.set("Burning Ship")
        self.landscape_type.set("Space")
        self.zoom.set(250.0)
        self.center_x.set(-1.768)
        self.center_y.set(-0.001)
        self.max_iter.set(200)
        self.power.set(2.0)
        self.thread_generate()

    def load_preset_dragons_breath(self):
        """Loads a preset for a 'Dragon's Breath' view in the Tricorn fractal."""
        self.fractal_type.set("Tricorn")
        self.landscape_type.set("Fire")
        self.zoom.set(150.0)
        self.center_x.set(-0.9)
        self.center_y.set(-0.3)
        self.max_iter.set(250)
        self.power.set(2.0)
        self.thread_generate()

    def export_image(self):
        """Exports the current fractal image to a file with robust error handling."""
        if not self.current_img:
            messagebox.showwarning("Export Failed", "No image has been generated yet to export.")
            return

        try:
            path = filedialog.asksaveasfilename(
                title="Export Image As",
                filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg")],
                defaultextension=".png"
            )
            if not path:
                self.logger.info("Image export cancelled by user.")
                return

            self.logger.info(f"Exporting image to {path}...")
            # For JPEG, we must convert to RGB as it doesn't support alpha
            export_img = self.current_img
            if path.lower().endswith(('.jpg', '.jpeg')):
                export_img = self.current_img.convert('RGB')

            export_img.save(path, quality=95) # Set quality for JPEG
            self.logger.info("Image export successful.")
            messagebox.showinfo("Success", f"Image successfully saved to:\n{path}")

        except Exception as e:
            self.logger.error(f"Failed to export image to {path}: {e}", exc_info=True)
            messagebox.showerror("Export Error", f"Could not save the image.\n\nError: {e}")

    def thread_animate(self):
        threading.Thread(target=self.export_animation).start()

    def export_animation(self):
        """Generates and exports a GIF animation with progress updates and error handling."""
        try:
            num_frames = self.num_frames.get()
            w, h = self.width.get(), self.height.get()
        except tk.TclError as e:
            self.logger.error(f"Invalid animation parameter: {e}")
            messagebox.showerror("Invalid Input", "Please ensure animation frames, width, and height are valid numbers.")
            return

        # Warn user about high memory usage for large animations
        total_pixels = w * h * num_frames
        if total_pixels > 30_000_000: # Approx. 150 frames at 800x600, or 30 at 1080p
            msg = (f"This animation ({num_frames} frames at {w}x{h}) is very large and may consume a lot of memory or take a long time.\n\n"
                   "Continue anyway?")
            if not messagebox.askyesno("High Memory Warning", msg):
                self.logger.info("Animation export cancelled by user due to high memory warning.")
                return

        path = filedialog.asksaveasfilename(defaultextension=".gif", filetypes=[("GIF Animation", "*.gif")])
        if not path:
            self.logger.info("Animation export cancelled by user.")
            return

        self.root.config(cursor="wait")
        self.progressbar.start()

        try:
            frames = []
            initial_zoom = self.zoom.get()
            self.logger.info(f"Starting animation export to {path} ({num_frames} frames)...")

            for i in range(num_frames):
                self.status_text.set(f"Generating animation frame {i + 1}/{num_frames}...")

                # Simple zoom-out animation logic
                self.zoom.set(initial_zoom * (1 + i * 0.2))

                iter_map = self._generate_fractal_map(w, h)
                fractal_img = self._color_fractal(iter_map)
                fractal_img = self._apply_filter(fractal_img)
                if self.invert_colors.get():
                    fractal_img = ImageOps.invert(fractal_img.convert('RGB'))

                # Composite the final frame
                final_frame = Image.new('RGBA', (w, h))
                if hasattr(self, 'background_img') and self.background_img:
                    bg = self.background_img.resize((w, h), Image.Resampling.LANCZOS)
                    final_frame.paste(bg.convert('RGBA'), (0, 0))
                final_frame.paste(fractal_img.convert('RGBA'), (0, 0), fractal_img.convert('RGBA'))
                if self.weave_mode.get() and self.sketch_img:
                    final_frame.paste(self.sketch_img, (0, 0), self.sketch_img)

                # For GIF, convert to RGB with a palette for smaller file size
                frames.append(final_frame.convert('P', palette=Image.ADAPTIVE))

            self.status_text.set("Saving GIF file...")
            self.zoom.set(initial_zoom)  # Reset zoom

            frames[0].save(path, save_all=True, append_images=frames[1:], loop=0, duration=self.frame_duration.get(), optimize=True)
            self.logger.info("Animation export successful.")
            messagebox.showinfo("Success", f"Animation successfully saved to:\n{path}")

        except Exception as e:
            self.logger.error(f"Animation export failed: {e}", exc_info=True)
            messagebox.showerror("Animation Error", f"Could not generate or save the animation.\n\nError: {e}")
        finally:
            self.status_text.set("Ready")
            self.root.config(cursor="")
            self.progressbar.stop()

    def change_appearance(self, mode):
        ctk.set_appearance_mode(mode)

    def show_about(self):
        """Displays the application's About dialog box."""
        title = f"About {APP_NAME}"
        message = (
            f"{APP_NAME} v{VERSION}\n\n"
            f"© {COPYRIGHT_YEAR} iD01t Productions, {AUTHOR}. All rights reserved.\n\n"
            f"Support: {CONTACT_EMAIL}\n"
            f"License: {LICENSE_INFO}"
        )
        messagebox.showinfo(title, message)

    def on_resize(self, event):
        self.update_preview()

if __name__ == "__main__":
    logger = setup_logging()
    try:
        root = ctk.CTk()
        app = FractalDreamWeaver(root, logger)
        root.mainloop()
    except Exception as e:
        logger.critical("A fatal error occurred during application initialization or runtime.", exc_info=True)
        messagebox.showerror("Fatal Error", f"A critical error occurred and the application must close:\n\n{e}")
        # sys.exit(1) # This can be uncommented for production release


# --- PYINSTALLER & TESTING NOTES ---
#
# === PyInstaller Build Command (for Windows) ===
# 1. Open a command prompt or terminal.
# 2. Navigate to the directory containing fractal.py.
# 3. Create and activate a virtual environment (recommended):
#    py -3.12 -m venv .venv
#    .venv\Scripts\activate
# 4. Install required packages:
#    pip install -U pip wheel
#    pip install pyinstaller pillow numpy customtkinter
#    pip install scipy  # Optional, for high-quality swirl filter
# 5. Run the PyInstaller command:
#    pyinstaller --name "FractalDreamWeaverPro" --onefile --noconsole --clean --optimize 2 ^
#      --hidden-import="PIL.Image" --hidden-import="PIL.ImageTk" ^
#      --hidden-import="PIL.ImageFilter" --hidden-import="PIL.ImageOps" ^
#      fractal.py
#
# === Acceptance Test Checklist ===
# [ ] 1. **App Launch & Resize**: App starts without errors. Window is resizable, UI elements adjust gracefully.
# [ ] 2. **Core Fractal Interaction**:
#       - [ ] Pan: In non-weave mode, left-click-drag pans the fractal.
#       - [ ] Zoom: Mouse wheel zooms in and out smoothly.
#       - [ ] Palette Change: Changing palettes in the menu updates the fractal colors.
#       - [ ] Nightmare Mode: Toggling adds controlled visual noise/distortion.
#       - [ ] Invert Colors: Toggles color inversion correctly.
# [ ] 3. **Weaving & Background**:
#       - [ ] Weave Mode: Toggling enables drawing on the canvas.
#       - [ ] Brush: Drawing with the brush works. Brush size and color can be changed.
#       - [ ] Clear Sketch: Button removes all drawings.
#       - [ ] Load Background: Loading a JPG/PNG places it behind the fractal.
# [ ] 4. **UI & Theme**:
#       - [ ] Appearance Switcher: 'light', 'dark', 'system' modes work and are readable.
#       - [ ] Parameter Controls: All sliders, menus, and checkboxes respond and trigger updates (if auto-update is on).
# [ ] 5. **Generation & Export**:
#       - [ ] Generate High-Res: Generate a 1600x1200 image with max_iter=750.
#       - [ ] Export PNG: Export the generated image as a PNG file. Check file integrity.
#       - [ ] Export JPEG: Export the same image as a JPEG. Check file integrity.
#       - [ ] Export Animation: Export a 48-frame GIF (e.g., 80ms/frame). Ensure UI is responsive during export and the final GIF animates correctly.
# [ ] 6. **Dependency Tests**:
#       - [ ] **Without SciPy**: Uninstall scipy (`pip uninstall scipy`). Run app. Verify all features work, especially the Swirl filter (should use NumPy fallback).
#       - [ ] **With SciPy**: Reinstall scipy (`pip install scipy`). Run app. Verify Swirl filter is high quality.
# [ ] 7. **Packaged EXE Test**:
#       - [ ] Build the EXE using the command above.
#       - [ ] Run the `.exe` from a different directory (e.g., Desktop).
#       - [ ] Verify it launches, generates, exports, and closes cleanly without errors.
#       - [ ] Check that `fractal_dream_weaver.log` is created next to the EXE.