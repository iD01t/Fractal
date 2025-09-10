import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
import customtkinter as ctk  # pip install customtkinter
import numpy as np
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageOps
from scipy.ndimage import map_coordinates  # pip install scipy if needed
import threading
import time  # For debounce

ctk.set_appearance_mode("dark")  # Modes: "system" (default), "light", "dark"
ctk.set_default_color_theme("dark-blue")  # Themes: "blue", "dark-blue", "green"

class FractalDreamWeaver:
    def __init__(self, root):
        self.root = root
        self.root.title("Fractal Dream Weaver Pro")
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
        self.thread_generate()

    def setup_ui(self):
        # Main frame
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Notebook for tabs (pro organization)
        notebook = ctk.CTkTabview(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: Preview
        preview_tab = notebook.add("Preview")
        self.preview_frame = ctk.CTkFrame(preview_tab)
        self.preview_frame.pack(fill=tk.BOTH, expand=True)
        self.preview_label = ctk.CTkLabel(self.preview_frame, text="")
        self.preview_label.pack(fill=tk.BOTH, expand=True)

        # Bind events for drawing/panning/zooming
        # Left mouse down begins drawing or panning depending on weave_mode
        self.preview_label.bind("<Button-1>", self.on_mouse_down)
        # Mouse drag while left button down
        self.preview_label.bind("<B1-Motion>", self.on_mouse_drag)
        # Release left mouse button
        self.preview_label.bind("<ButtonRelease-1>", self.on_mouse_up)
        # Mouse wheel zoom
        self.preview_label.bind("<MouseWheel>", self.on_mouse_wheel)

        # Status bar
        status_bar = ctk.CTkLabel(preview_tab, textvariable=self.status_text, anchor="w")
        status_bar.pack(fill=tk.X, pady=5)
        # Progress bar (indeterminate) to show generation status
        self.progressbar = ctk.CTkProgressBar(preview_tab, orientation="horizontal", mode="indeterminate")
        self.progressbar.pack(fill=tk.X, pady=5)
        
        # Tab 2: Parameters
        param_tab = notebook.add("Parameters")
        param_frame = ctk.CTkScrollableFrame(param_tab)
        param_frame.pack(fill=tk.BOTH, expand=True)
        
        # Fractal Params Section
        fractal_section = ctk.CTkFrame(param_frame)
        fractal_section.pack(fill=tk.X, pady=10)
        ctk.CTkLabel(fractal_section, text="Fractal Settings").pack()
        
        ctk.CTkLabel(fractal_section, text="Width").pack()
        ctk.CTkEntry(fractal_section, textvariable=self.width).pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Height").pack()
        ctk.CTkEntry(fractal_section, textvariable=self.height).pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Zoom").pack()
        self.zoom_slider = ctk.CTkSlider(fractal_section, variable=self.zoom, from_=0.1, to=1000, command=self.slider_changed)
        self.zoom_slider.pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Center X").pack()
        self.center_x_slider = ctk.CTkSlider(fractal_section, variable=self.center_x, from_=-2.5, to=2.5, command=self.slider_changed)
        self.center_x_slider.pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Center Y").pack()
        self.center_y_slider = ctk.CTkSlider(fractal_section, variable=self.center_y, from_=-2.0, to=2.0, command=self.slider_changed)
        self.center_y_slider.pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Max Iterations").pack()
        self.max_iter_slider = ctk.CTkSlider(fractal_section, variable=self.max_iter, from_=50, to=1000, command=self.slider_changed)
        self.max_iter_slider.pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Power").pack()
        self.power_slider = ctk.CTkSlider(fractal_section, variable=self.power, from_=1.5, to=5.0, command=self.slider_changed)
        self.power_slider.pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Julia C Real").pack()
        self.c_real_slider = ctk.CTkSlider(fractal_section, variable=self.c_real, from_=-2.0, to=2.0, command=self.slider_changed)
        self.c_real_slider.pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Julia C Imag").pack()
        self.c_imag_slider = ctk.CTkSlider(fractal_section, variable=self.c_imag, from_=-2.0, to=2.0, command=self.slider_changed)
        self.c_imag_slider.pack(fill=tk.X)
        
        ctk.CTkLabel(fractal_section, text="Fractal Type").pack()
        ctk.CTkOptionMenu(fractal_section, variable=self.fractal_type, values=["Mandelbrot", "Julia", "Burning Ship", "Tricorn"], command=self.param_changed).pack(fill=tk.X)
        
        # Landscape Section
        landscape_section = ctk.CTkFrame(param_frame)
        landscape_section.pack(fill=tk.X, pady=10)
        ctk.CTkLabel(landscape_section, text="Landscape Settings").pack()
        
        ctk.CTkLabel(landscape_section, text="Landscape Type").pack()
        # Extended palette options: added additional themes for more creative control
        landscape_options = [
            "Forest", "City", "Dream", "Ocean", "Desert", "Space",
            "Rainbow", "Fire", "Ice", "Inferno"
        ]
        ctk.CTkOptionMenu(landscape_section, variable=self.landscape_type, values=landscape_options, command=self.param_changed).pack(fill=tk.X)
        
        ctk.CTkCheckBox(landscape_section, text="Nightmare Mode", variable=self.nightmare_mode, command=self.param_changed).pack()
        ctk.CTkCheckBox(landscape_section, text="Invert Colors", variable=self.invert_colors, command=self.param_changed).pack()
        
        # Filter Section
        filter_section = ctk.CTkFrame(param_frame)
        filter_section.pack(fill=tk.X, pady=10)
        ctk.CTkLabel(filter_section, text="Filter Settings").pack()
        
        ctk.CTkLabel(filter_section, text="Filter").pack()
        ctk.CTkOptionMenu(filter_section, variable=self.filter_type, values=["None", "Blur", "Edge", "Invert", "Swirl", "Emboss", "Sharpen", "Contour"], command=self.param_changed).pack(fill=tk.X)
        
        # Weave Section
        weave_section = ctk.CTkFrame(param_frame)
        weave_section.pack(fill=tk.X, pady=10)
        ctk.CTkLabel(weave_section, text="Weave & Draw").pack()
        
        ctk.CTkCheckBox(weave_section, text="Weave Mode", variable=self.weave_mode, command=self.param_changed).pack()
        ctk.CTkLabel(weave_section, text="Brush Size").pack()
        ctk.CTkSlider(weave_section, variable=self.brush_size, from_=1, to=20).pack(fill=tk.X)
        ctk.CTkButton(weave_section, text="Clear Sketch", command=self.clear_sketch).pack(fill=tk.X, pady=5)
        ctk.CTkButton(weave_section, text="Load Background Image", command=self.load_background).pack(fill=tk.X, pady=5)

        # New: Brush color chooser for creative weaving
        ctk.CTkButton(weave_section, text="Brush Color", command=self.choose_brush_color).pack(fill=tk.X, pady=5)
        
        # Animation Section
        anim_section = ctk.CTkFrame(param_frame)
        anim_section.pack(fill=tk.X, pady=10)
        ctk.CTkLabel(anim_section, text="Animation Settings").pack()
        
        ctk.CTkLabel(anim_section, text="Num Frames").pack()
        ctk.CTkEntry(anim_section, textvariable=self.num_frames).pack(fill=tk.X)
        
        ctk.CTkLabel(anim_section, text="Frame Duration (ms)").pack()
        ctk.CTkEntry(anim_section, textvariable=self.frame_duration).pack(fill=tk.X)
        
        # Controls Section
        controls_section = ctk.CTkFrame(param_frame)
        controls_section.pack(fill=tk.X, pady=10)
        ctk.CTkLabel(controls_section, text="Controls").pack()
        
        ctk.CTkCheckBox(controls_section, text="Auto Update", variable=self.auto_update).pack()
        ctk.CTkButton(controls_section, text="Generate", command=self.thread_generate).pack(fill=tk.X, pady=5)
        ctk.CTkButton(controls_section, text="Export Image", command=self.export_image).pack(fill=tk.X, pady=5)
        ctk.CTkButton(controls_section, text="Export Animation", command=self.thread_animate).pack(fill=tk.X, pady=5)
        
        # Presets Button (New cool function)
        ctk.CTkButton(controls_section, text="Load Preset: Spiral", command=self.load_preset_spiral).pack(fill=tk.X, pady=5)
        ctk.CTkButton(controls_section, text="Load Preset: Seahorse", command=self.load_preset_seahorse).pack(fill=tk.X, pady=5)
        
        # Theme Toggle
        ctk.CTkLabel(controls_section, text="Appearance Mode").pack()
        ctk.CTkOptionMenu(controls_section, variable=self.appearance_mode, values=["light", "dark", "system"], command=self.change_appearance).pack(fill=tk.X)
        
        # About Button
        ctk.CTkButton(controls_section, text="About", command=self.show_about).pack(fill=tk.X, pady=5)

    def slider_changed(self, value):
        if self.auto_update.get():
            self.thread_generate()

    def param_changed(self, value=None):
        if self.auto_update.get():
            self.thread_generate()

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
        try:
            w, h = self.width.get(), self.height.get()
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
                img = ImageOps.invert(img)

            # Blend sketch or background if weave mode
            if self.weave_mode.get():
                if hasattr(self, 'background_img'):
                    bg = self.background_img.copy()
                    img = Image.alpha_composite(bg.convert('RGBA'), img.convert('RGBA'))
                img = img.convert('RGBA')
                img.paste(self.sketch_img, (0, 0), self.sketch_img)

            # Store original image
            self.current_img = img

            # Display resized to fit preview
            self.update_preview()
        except Exception as e:
            # Show error message in the main thread
            self.root.after(0, lambda: messagebox.showerror("Error", f"Generation failed: {str(e)}"))
        finally:
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
        """
        Handle mouse button press on the preview. If weave mode is enabled, begin
        drawing; otherwise begin panning by remembering the starting pixel and
        current center.
        """
        if self.weave_mode.get():
            # Use existing drawing logic
            self.start_draw(event)
        else:
            # Begin panning: record starting pixel and fractal center
            self.panning = True
            self.pan_start_px = event.x
            self.pan_start_py = event.y
            self.pan_center_x = self.center_x.get()
            self.pan_center_y = self.center_y.get()
            self.last_pan_time = time.time()

    def on_mouse_drag(self, event):
        """
        Handle mouse drag. If weaving, draw on the sketch. Otherwise, update
        fractal center based on drag distance to allow panning. Real-time updates
        are throttled to avoid excessive redraws.
        """
        if self.weave_mode.get():
            self.draw_line(event)
        else:
            if self.panning:
                # Compute pixel difference
                dx_px = event.x - self.pan_start_px
                dy_px = event.y - self.pan_start_py
                # Calculate fractal coordinate range based on zoom
                zoom = self.zoom.get()
                frac_range_x = 5.0 / zoom
                frac_range_y = 4.0 / zoom
                # Map pixel delta to fractal coordinate delta
                # Negative sign for y to invert vertical axis
                new_center_x = self.pan_center_x - dx_px * (frac_range_x / max(self.preview_frame.winfo_width(), 1))
                new_center_y = self.pan_center_y - dy_px * (frac_range_y / max(self.preview_frame.winfo_height(), 1))
                # Update center variables
                self.center_x.set(new_center_x)
                self.center_y.set(new_center_y)
                # Throttle updates to improve performance
                current_time = time.time()
                if current_time - self.last_pan_time > 0.15:
                    self.last_pan_time = current_time
                    self.thread_generate()

    def on_mouse_up(self, event):
        """
        Finish drawing or panning when the mouse button is released. If panning,
        trigger a final update to ensure the image matches the last position.
        """
        if self.weave_mode.get():
            # End drawing by resetting last position
            self.last_pos = None
        else:
            # End panning and trigger final generation
            if self.panning:
                self.panning = False
                self.thread_generate()

    def on_mouse_wheel(self, event):
        """
        Handle mouse wheel to zoom in and out. A positive delta zooms in,
        negative zooms out. Update the fractal after adjusting the zoom.
        """
        # Determine zoom factor; event.delta is positive for scroll up on Windows
        if event.delta > 0:
            new_zoom = self.zoom.get() * 1.2
        else:
            new_zoom = self.zoom.get() / 1.2
        # Clamp zoom to a sensible range to avoid too small or too large values
        new_zoom = max(0.1, min(new_zoom, 10000))
        self.zoom.set(new_zoom)
        self.thread_generate()

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
        
        x_min = center_x - 2.5 / zoom
        x_max = center_x + 2.5 / zoom
        y_min = center_y - 2.0 / zoom
        y_max = center_y + 2.0 / zoom
        
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
            # Enhanced nightmare: noise + slight distortion
            noise = np.random.randint(-30, 30, colors.shape)
            colors = np.clip(colors + noise, 0, 255).astype(np.uint8)
            # Simple random shift distortion
            shift = np.random.randint(-2, 3, (2,))
            colors = np.roll(colors, shift, axis=(0,1))
        
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
        elif filter_type == "Emboss":
            img = img.filter(ImageFilter.EMBOSS)
        elif filter_type == "Sharpen":
            img = img.filter(ImageFilter.SHARPEN)
        elif filter_type == "Contour":
            img = img.filter(ImageFilter.CONTOUR)
        return img

    def start_draw(self, event):
        if self.weave_mode.get():
            scale_x = self.width.get() / self.preview_frame.winfo_width()
            scale_y = self.height.get() / self.preview_frame.winfo_height()
            self.last_pos = (int(event.x * scale_x), int(event.y * scale_y))

    def draw_line(self, event):
        if self.weave_mode.get() and self.last_pos:
            scale_x = self.width.get() / self.preview_frame.winfo_width()
            scale_y = self.height.get() / self.preview_frame.winfo_height()
            current_pos = (int(event.x * scale_x), int(event.y * scale_y))
            self.sketch_draw.line([self.last_pos, current_pos], fill=self.brush_color, width=self.brush_size.get())
            self.last_pos = current_pos
            # Debounce generate
            if self.debounce_id:
                self.root.after_cancel(self.debounce_id)
            self.debounce_id = self.root.after(self.debounce_delay, self.thread_generate)

    def clear_sketch(self):
        self.sketch_img = Image.new('RGBA', (self.width.get(), self.height.get()), (255, 255, 255, 0))
        self.sketch_draw = ImageDraw.Draw(self.sketch_img)
        self.thread_generate()

    def load_background(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if path:
            self.background_img = Image.open(path)
            self.thread_generate()

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

    def export_image(self):
        if hasattr(self, 'current_img'):
            path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
            if path:
                self.current_img.save(path)
                messagebox.showinfo("Success", "Image exported!")

    def thread_animate(self):
        threading.Thread(target=self.export_animation).start()

    def export_animation(self):
        self.status_text.set("Animating...")
        self.root.config(cursor="wait")
        try:
            frames = []
            initial_zoom = self.zoom.get()
            w, h = self.width.get(), self.height.get()
            for i in range(self.num_frames.get()):
                self.zoom.set(initial_zoom * (1 + i / 5.0))  # Enhanced zoom animation
                iter_map = self._generate_fractal_map(w, h)
                colors = self._color_fractal(iter_map)
                img = Image.fromarray(colors, 'RGB')
                img = self._apply_filter(img)
                if self.invert_colors.get():
                    img = ImageOps.invert(img)
                if self.weave_mode.get():
                    if hasattr(self, 'background_img'):
                        bg = self.background_img.resize((w, h), Image.Resampling.LANCZOS)
                        img = Image.alpha_composite(bg.convert('RGBA'), img.convert('RGBA'))
                    img = img.convert('RGBA')
                    img.paste(self.sketch_img, (0, 0), self.sketch_img)
                frames.append(img)
            self.zoom.set(initial_zoom)  # Reset
            path = filedialog.asksaveasfilename(defaultextension=".gif", filetypes=[("GIF", "*.gif")])
            if path:
                frames[0].save(path, save_all=True, append_images=frames[1:], loop=0, duration=self.frame_duration.get())
                messagebox.showinfo("Success", "Animation exported!")
        except Exception as e:
            messagebox.showerror("Error", f"Animation failed: {str(e)}")
        finally:
            self.status_text.set("Ready")
            self.root.config(cursor="")

    def change_appearance(self, mode):
        ctk.set_appearance_mode(mode)

    def show_about(self):
        messagebox.showinfo("About", "Fractal Dream Weaver Pro v1.0\nCreated for itch.io\nEnjoy generating infinite art!")

    def on_resize(self, event):
        self.update_preview()

if __name__ == "__main__":
    root = ctk.CTk()
    app = FractalDreamWeaver(root)
    root.mainloop()