from pathlib import Path
import moderngl_window as mglw
import moderngl
import math
import sys
from PIL import Image
import dearpygui.dearpygui as dpg
import numpy as np

#default
Height = 1080 
Width = 1920

def resource_path(relative_path: str) -> Path:
    try:
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        base_path = Path(__file__).parent
    return base_path / relative_path

def vrotate_p(v, sin_p, cos_p, sin_y, cos_y):
    x, y, z = v
    y2 = z * sin_p + y * cos_p
    z2 = z * cos_p - y * sin_p
    x3 = x * cos_y + z2 * sin_y
    z3 = -x * sin_y + z2 * cos_y
    return (x3, y2, z3)
    
class fractal_Path_tracer(mglw.WindowConfig):
    gl_version = (4, 3)
    title = "Fractal Path tracer"
    window_size = (Width , Height)
    aspect_ratio = None
    resizable = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.frame = 0
        self.iCam_pos = [0.1, 0.1, -5.0]
        self.iCam_yp = [0.0, 0.0]
        self.iMode = 0
        self.iCam_a = 0.01
        self.cam_speed = 2.0
        #Studio/Sky, Light Size, rotation, elevation, power, contrast
        self.World_settings = [0.0,1.0,120.0,30.0,1.0,1.0]
        #bounces, ni, normal quality
        self.Render_settings = [5,512,0.001,90.0,0.0005,0.25]
        #gamma, exposure, brightness, saturation, contrast, chro, highlights
        self.Post_settings = [0.0,1.0,0.0,1.0,1.0,0.0,0.0]
        self.SET = [0.0 ,0.0 ,0.0 ,0.0 ,0.0 ,0.0 ,0.0 ,0.0]

        self.prev_keys = set()
        self.keys_down = set()

        self._fps_time_accum = 0.0
        self._fps_frame_accum = 0.0
        self._last_fps = 0.0

        self.sin_p = math.sin(self.iCam_yp[1])
        self.cos_p = math.cos(self.iCam_yp[1])
        self.sin_y = math.sin(self.iCam_yp[0])
        self.cos_y = math.cos(self.iCam_yp[0])


        self.ui_render_width, self.ui_render_height = self.wnd.size
        self.pending_resize = None
        self.pending_window_resize = None
        self.hdri_tex = None
        self.pending_hdri = None
        self.request_recompile = False
        self.request_save_render = False

        self.default_ui_scale = 0.3

        dpg.create_context()
        self.load_fonts()
        self.setup_ui()

        post_code = resource_path("PostProcess.glsl").read_text()
        self.vertex_shader_source = """
        #version 430 core
        in vec2 in_position;
        void main() {
            gl_Position = vec4(in_position, 0.0, 1.0);
        }
        """

        fragment_shader = self.build_fragment_shader(
            dpg.get_value(self.user_helper_editor),
            dpg.get_value(self.user_sdf_editor),
        )

        post_fragment_shader = f"""
        #version 430 core
        out vec4 fragColor;
        
        uniform sampler2D uAccum;
        uniform vec3 iResolution;
        uniform float Post_settings[7];
        
        {post_code}
        
        void main()
        {{
            postProcess(fragColor, gl_FragCoord.xy);
        }}
        """




        self.program = self.ctx.program(
            vertex_shader=self.vertex_shader_source,
            fragment_shader=fragment_shader,
        )
        if "HDRI" in self.program:
            self.program["HDRI"].value = 1

        self.post_program = self.ctx.program(
            vertex_shader=self.vertex_shader_source,
            fragment_shader=post_fragment_shader,
        )
        # fallback texture so sampler is always valid
        self.hdri_tex = self.ctx.texture((1, 1), 3, b"\xff\xff\xff")
        self.hdri_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.hdri_tex.use(location=1)

        self.quad = mglw.geometry.quad_2d(size=(2.0, 2.0))

        w = self.wnd.buffer_width
        h = self.wnd.buffer_height

        self.accum_textures = [
            self.ctx.texture((w, h), components=4, dtype="f4"),
            self.ctx.texture((w, h), components=4, dtype="f4"),
        ]

        for tex in self.accum_textures:
            tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            tex.repeat_x = False
            tex.repeat_y = False
        self.fbos = [
            self.ctx.framebuffer(color_attachments=[self.accum_textures[0]]),
            self.ctx.framebuffer(color_attachments=[self.accum_textures[1]]),
        ]
        self.ping = 0
        self.pong = 1


    def save_screenshot(self):
        self.ctx.finish()
        w = self.wnd.buffer_width
        h = self.wnd.buffer_height
        screenshot_tex = self.ctx.texture((w, h), components=4) 
        screenshot_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    
        screenshot_fbo = self.ctx.framebuffer(
            color_attachments=[screenshot_tex]
        )
    
        if self.iMode == 0:
            screenshot_fbo.use()
            self.ctx.viewport = (0, 0, w, h)
            self.quad.render(self.program)
    
        else:    
            screenshot_fbo.use()
            self.ctx.viewport = (0, 0, w, h)
    
            # Bind accumulated HDR texture
            self.accum_textures[self.ping].use(location=0)
    
            if "uAccum" in self.post_program:
                self.post_program["uAccum"].value = 0
    
            if "iResolution" in self.post_program:
                self.post_program["iResolution"].value = (float(w), float(h), 1.0)

            self.post_program["Post_settings"].value = tuple(float(x) for x in self.Post_settings)
    
            self.quad.render(self.post_program)
    
        data = screenshot_fbo.read(components=3, alignment=1)
    
        screenshot_fbo.release()
        screenshot_tex.release()
    
        image = Image.frombytes("RGB", (w, h), data)
        image = image.transpose(Image.FLIP_TOP_BOTTOM)

        existing = sorted(Path(".").glob("Render*.png"))
        
        if existing:
            numbers = [int(f.stem.replace("Render", "")) for f in existing if f.stem.replace("Render","").isdigit()]
            number = max(numbers) + 1 if numbers else 1
        else:
            number = 1
        
        filename = Path(f"Render{number:03d}.png")
        image.save(filename)


    def on_render_button(self, sender):
        self.request_save_render = True


    def build_user_sdf_function(self, body: str) -> str:
        return f"""
        SDFResult UserSDF(vec3 p)
        {{
            SDFResult r;
            r.material = defaultMaterial();
        
            Material material = r.material;
            float sdf = inf;
        
            // ---- USER CODE ----
            {body}
            // -------------------
        
            r.material = material;    
            r.distance = sdf;
            return r;
        }}
        """
    def build_user_helper_functions(self, body: str) -> str:
        return f"""
        {body}
        """
    def recompile(self):
        self.request_recompile = True
    def build_fragment_shader(self, user_helpers: str, user_sdf_body: str) -> str:
        base_code = resource_path("Shader.glsl").read_text()

        helper_code = self.build_user_helper_functions(user_helpers)
        user_sdf_code = self.build_user_sdf_function(user_sdf_body)

        base_code = base_code.replace("{{USER_HELPERS}}", helper_code)
        base_code = base_code.replace("{{USER_SDF}}", user_sdf_code)


        return f"""
        #version 430 core
        out vec4 fragColor;
    
        uniform vec3 iResolution;
        uniform float iTime;
        uniform int iFrame;
        uniform vec3 iCam_Pos;
        uniform vec2 iCam_yp;
        uniform float iCam_a;
        uniform int iMode;
        
        uniform sampler2D iPrevFrame;
        uniform sampler2D HDRI;
        
        uniform float World_settings[6];
        uniform float SET[8];
        uniform float Render_settings[6];
    
        {base_code}
    
        void main()
        {{
            mainImage(fragColor, gl_FragCoord.xy);
        }}
        """
    
    #resolution--------------------------------
    def on_resize(self, width: int, height: int):
        self.resize_accumulation_buffers(width, height)
    
        self.ui_render_width = width
        self.ui_render_height = height
    
        dpg.set_value("render_width_input", width)
        dpg.set_value("render_height_input", height)

    def resize_accumulation_buffers(self, width, height):
        if not hasattr(self, "accum_textures"):
            return
    
        self.ctx.finish()
    
        for tex in self.accum_textures:
            tex.release()
        for fbo in self.fbos:
            fbo.release()
    
        self.accum_textures = [
            self.ctx.texture((width, height), components=4, dtype="f4"),
            self.ctx.texture((width, height), components=4, dtype="f4"),
        ]
    
        for tex in self.accum_textures:
            tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            tex.repeat_x = False
            tex.repeat_y = False
    
        self.fbos = [
            self.ctx.framebuffer(color_attachments=[self.accum_textures[0]]),
            self.ctx.framebuffer(color_attachments=[self.accum_textures[1]]),
        ]

        for fbo in self.fbos:
            fbo.use()
            fbo.clear(0.0, 0.0, 0.0, 0.0)
    
        self.ping = 0
        self.pong = 1
        self.frame = 0

    def apply_render_resolution(self):
        w = max(64, int(self.ui_render_width))
        h = max(64, int(self.ui_render_height))
        self.pending_window_resize = (w, h)
        
    
    #ui-------------------------------   
    def on_SDF_settings_slider(self, sender, value, user_data):
        self.SET[user_data] = float(value)
        self.frame = 0
    def on_world_env_change(self, sender, app_data):
        if app_data == "Studio":
            self.World_settings[0] = 0
        elif app_data == "Sky":
            self.World_settings[0] = 1
        elif app_data == "HDRI":
            self.World_settings[0] = 2
    
        self.frame = 0
    def on_world_slider(self, sender, value, user_data):
        self.World_settings[user_data] = float(value)
        self.frame = 0
    def on_render_slider(self, sender, value, user_data):
        self.Render_settings[user_data] = float(value)
        self.frame = 0
        
    def close(self):
        if hasattr(self, "accum_textures"):
            for tex in self.accum_textures:
                if tex:
                    tex.release()
        if hasattr(self, "fbos"):
            for fbo in self.fbos:
                if fbo:
                    fbo.release()
        if hasattr(self, "program") and self.program:
            self.program.release()
        if hasattr(self, "post_program") and self.post_program:
            self.post_program.release()
        dpg.destroy_context()
        super().close()


    #post----------------------
    def on_gamma_change(self, sender, app_data):
        if app_data == "SRGB": self.Post_settings[0] = 0
        if app_data == "REC.709": self.Post_settings[0] = 1
        if app_data == "DCI-P3": self.Post_settings[0] = 2
        if app_data == "ACES": self.Post_settings[0] = 3
        if app_data == "RAW": self.Post_settings[0] = 4
    def on_post_slider(self, sender, value, user_data):
        self.Post_settings[user_data] = float(value)

    def load_hdri_callback(self, sender, app_data):
        if not app_data or not app_data.get("file_path_name"):
            return
        path = app_data["file_path_name"]
        try:
            import imageio.v2 as imageio 
            img = imageio.imread(path)

            if img.ndim == 2:
                img = np.stack([img, img, img], axis=-1)
    
            if img.shape[2] > 3:
                img = img[:, :, :3]

            if img.dtype != np.uint8:
                img = np.clip(img, 0, 1)
                img = (img * 255).astype(np.uint8)
    
            h, w, _ = img.shape
            data = img.tobytes()
    
            self.pending_hdri = (w, h, data)
    
        except Exception as e:
            print("HDRI load failed:", e)


    def load_fonts(self):
    
        font_path = resource_path("fonts/JetBrainsMono-Regular.ttf")
    
        with dpg.font_registry():
            self.font = dpg.add_font(str(font_path), 64) 
    
        dpg.bind_font(self.font)
        
    def set_ui_scale(self, sender, app_data):
    
        scale_map = {
            "70%": self.default_ui_scale * 0.85,
            "100%": self.default_ui_scale,
            "130%": self.default_ui_scale * 1.33,
            "160%": self.default_ui_scale * 1.66,
            "200%": self.default_ui_scale * 2.0
        }
    
        dpg.set_global_font_scale(scale_map[app_data])
    

        
        
        
        
    def on_key_event(self, key, action, modifiers):
        keys = self.wnd.keys
        if action == keys.ACTION_PRESS:
            self.keys_down.add(key)
        elif action == keys.ACTION_RELEASE:
            self.keys_down.discard(key)            
            


    #UI---------------------------------------------------------------------------------------------------------------UI

    def setup_ui(self):

        with dpg.file_dialog(
                directory_selector=False,
                show=False,
                callback=self.load_hdri_callback,
                tag="hdri_file_dialog",
                width=700,
                height=400):
            dpg.add_file_extension(".hdr", color=(255, 255, 0, 255), custom_text="HDRI (*.hdr)")
            
        with dpg.window(
                label="Help",
                modal=True,
                show=False,
                tag="help_popup",
                no_title_bar=False,
                width=360,
                height=220,
        ):
            dpg.add_text("Fractal Path Tracer")
            dpg.add_separator()
            dpg.add_text(
                " WASD / QE : Move camera\n"
                " Arrow keys : Rotate camera\n"
                " R : Toggle render / preview\n"
                " Ctrl + A / D : Depth of field\n"
                " Ctrl + S : Save render\n"
                " Shift : go faster! \n"
                " Shift + Space : go even faster!! \n"
                "\n"
                " Edit the GLSL SDF code and press\n"
                " 'Recompile SDF' to update.\n"
                "\n"
                " Added GLSL function:\n"
                " Hsv2rgb( vec3(H,S,V) ) - Hsv to Rgb\n"
                " Smin(a,b,k) - Smooth Min\n"
            )
            dpg.add_spacer(height=10)
            dpg.add_button(label="Close", callback=lambda: dpg.configure_item("help_popup", show=False))

        with dpg.window(
                label="Object Controls",
                tag="main_ui",
                width=-1,
                height=-1,
                no_close=True,
                no_collapse=True,
                no_move=True,
                no_resize=True
        ):
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp):
            
                dpg.add_table_column(width_fixed=True) 
                dpg.add_table_column(width_fixed=True)  
                dpg.add_table_column(width_fixed=True)  
                dpg.add_table_column(width_fixed=True)   
                dpg.add_table_column()                  
                dpg.add_table_column(width_fixed=True)  
            
                with dpg.table_row():
                    dpg.add_button(
                        label="?",
                        callback=lambda: dpg.configure_item("help_popup", show=True)
                    )
            
                    dpg.add_spacer(width=10)
            
                    dpg.add_text("UI scale")
            
                    dpg.add_combo(
                        items=["70%", "100%", "130%", "160%", "200%"],
                        default_value="100%",
                        width=100,
                        callback=self.set_ui_scale
                    )
            
                    dpg.add_spacer()
            
                    dpg.add_button(
                        label="Save Render!",
                        callback=self.on_render_button
                    )

            dpg.add_separator()
            with dpg.collapsing_header(label="SDF Editor", default_open=False):
                with dpg.child_window(
                        height=440,
                        border=True
                ):
                    with dpg.collapsing_header(label="Helper Functions", default_open=False):
                        self.user_helper_editor = dpg.add_input_text(
                            label="",
                            multiline=True,
                            height=360,
                            width= -1,
                            default_value=(
                                "// made by: michael0884\n"
                                "vec2 De( vec3 p) {\n"
                                "  float orbittrap = 0.0;\n"
                                "  float scale = 1.9 ;\n"
                                "  float angle1 = -9.83 + SET[0]/2. ;\n"
                                "  float angle2 = -1.16 + SET[1]/2.;\n"
                                "  vec3 shift = vec3( -3.508, -3.593, 3.295 + SET[2] * 7.);\n"
                                "  vec2 a1 = vec2(sin(angle1), cos(angle1));\n"
                                "  vec2 a2 = vec2(sin(angle2), cos(angle2));\n"
                                "  mat2 rmZ = mat2(a1.y, a1.x, -a1.x, a1.y);\n"
                                "  mat2 rmX = mat2(a2.y, a2.x, -a2.x, a2.y);\n"
                                "  float s = 1.0;\n"
                                "  for (int i = 0; i <20; ++i){\n"
                                "    p.xyz = abs(p.xyz);\n"
                                "    p.xy *= rmZ;\n"
                                "    p.xy += min( p.x - p.y, 0.0 ) * vec2( -1., 1. );\n"
                                "    p.xz += min( p.x - p.z, 0.0 ) * vec2( -1., 1. );\n"
                                "    p.yz += min( p.y - p.z, 0.0 ) * vec2( -1., 1. );\n"
                                "    p.yz *= rmX;\n"
                                "    p *= scale;\n"
                                "    s *= scale;\n"
                                "    p.xyz += shift;\n"
                                "    orbittrap = max( orbittrap, p.z/p.y/p.x);\n"
                                "  }\n"
                                "  vec3 d = abs( p ) - vec3( 6.0f );\n"
                                "  float sdf = ( min( max( d.x, max( d.y, d.z ) ), 0.0 ) + length( max( d, 0.0 ) ) ) / s;\n"
                                "  return vec2(sdf, clamp( sin(orbittrap),0.,1.0) );\n"
                                "}\n"
                            )
                        )

                    with dpg.collapsing_header(label="SDF", default_open=True):
                        self.user_sdf_editor = dpg.add_input_text(
                            label="",
                            multiline=True,
                            height=360,
                            width= -1,
                            default_value=(
                                "//example sdf\n"
                                "vec2 fractal = De(p);\n"
                                "sdf = fractal.x;\n"
                                "\n"
                                "vec3 HSV = vec3( fractal.y/2. + 0.3 ,0.5 ,1.);\n"
                                "\n"
                                "material.rgb = Hsv2rgb(HSV);\n"
                                "material.roughness = 1.0;\n"
                                "material.specular = 0.0;\n"
                                "material.ior = 1.5;\n"
                                "material.specularRoughness = 0.0;\n"
                                "material.emission = 0.0;\n"

                            )
                        )

                dpg.add_separator()
                dpg.add_button(
                    label="Recompile SDF",
                    callback=self.recompile
                )
                self.sdf_compile_log = dpg.add_text("")

                dpg.add_separator()
                with dpg.child_window(
                        height=140,
                        border=True
                ):
                    with dpg.collapsing_header(
                            label="SDF settings",
                            default_open=True
                    ):
                        for i in range(8):
                            dpg.add_slider_float(
                                label=f"SET[{i}]",
                                min_value=-1.0,
                                max_value=1.0,
                                default_value=0.0,
                                callback=self.on_SDF_settings_slider,
                                user_data=i
                            )

            dpg.add_separator()
            with dpg.collapsing_header(label="World Controls", default_open=False):

                dpg.add_combo(
                    label="Environment",
                    items=["Studio", "Sky", "HDRI"],
                    default_value="Studio",
                    callback=self.on_world_env_change
                )
                dpg.add_button(
                    label="Load HDRI",
                    callback=lambda: dpg.show_item("hdri_file_dialog")
                )
                dpg.add_slider_float(
                    label="Light Size",
                    min_value=0.0,
                    max_value=2.0,
                    default_value=self.World_settings[1],
                    callback=self.on_world_slider,
                    user_data=1
                )
                dpg.add_slider_float(
                    label="Rotation",
                    min_value=0.0,
                    max_value=360,
                    default_value=self.World_settings[2],
                    callback=self.on_world_slider,
                    user_data=2
                )
                dpg.add_slider_float(
                    label="Light Elevation",
                    min_value=0.0,
                    max_value=360,
                    default_value=self.World_settings[3],
                    callback=self.on_world_slider,
                    user_data=3
                )
                dpg.add_input_float(
                    label="Power",
                    default_value=self.World_settings[4],
                    callback=self.on_world_slider,
                    user_data=4
                )
                dpg.add_input_float(
                    label="Contrast",
                    default_value=self.World_settings[5],
                    callback=self.on_world_slider,
                    user_data=5,
                    step = 0.01
                )



                dpg.add_separator()
            with dpg.collapsing_header(label="Render Settings", default_open=False):

                dpg.add_input_float(
                    label="Fov",
                    min_value=0.0,
                    max_value=180,
                    default_value=self.Render_settings[3],
                    callback=self.on_render_slider,
                    user_data=3,
                    step=2.,
                )
                dpg.add_input_int(
                    label="Bounces",
                    default_value=int(self.Render_settings[0]),
                    callback=self.on_render_slider,
                    user_data=0
                )
                dpg.add_input_int(
                    label="Ray Quality",
                    default_value=int(self.Render_settings[1]),
                    callback=self.on_render_slider,
                    user_data=1
                )
                dpg.add_input_float(
                    label="Normal Epsilon",
                    default_value=self.Render_settings[2],
                    callback=self.on_render_slider,
                    user_data=2,
                    step=0.00005,
                    format="%.6f"
                )
                dpg.add_input_float(
                    label="Min Distance",
                    default_value=self.Render_settings[4],
                    callback=self.on_render_slider,
                    user_data=4,
                    step=0.00005,
                    format="%.6f"
                )
                dpg.add_slider_float(
                    label="Optimization",
                    default_value=self.Render_settings[5],
                    min_value=0,
                    max_value=1,
                    callback=self.on_render_slider,
                    user_data=5
                )
                dpg.add_separator()
                dpg.add_text("Render Resolution")
                
                dpg.add_input_int(
                    label="Width",
                    tag="render_width_input",
                    default_value=self.ui_render_width,
                    min_value=64,
                    max_value=16384,
                    callback=lambda s, a: setattr(self, "ui_render_width", a),
                    width=180
                )
                
                dpg.add_input_int(
                    label="Height",
                    tag="render_height_input",
                    default_value=self.ui_render_height,
                    min_value=64,
                    max_value=16384,
                    callback=lambda s, a: setattr(self, "ui_render_height", a),
                    width=180
                )
                
                dpg.add_button(
                    label="Apply Resolution",
                    width=280,
                    callback=lambda: self.apply_render_resolution()
                )                
                
            dpg.add_separator()
            with dpg.collapsing_header(label="Color Management", default_open=False):

                dpg.add_combo(
                    label="Gamma",
                    items=["SRGB", "REC.709", "DCI-P3", "ACES", "RAW"],
                    default_value="SRGB",
                    callback=self.on_gamma_change
                )
                dpg.add_slider_float(
                    label="Exposure",
                    min_value=0.0,
                    max_value=3.0,
                    default_value=self.Post_settings[1],
                    callback=self.on_post_slider,
                    user_data=1
                )
                dpg.add_slider_float(
                    label="Brightness",
                    min_value=-1.0,
                    max_value=1.0,
                    default_value=self.Post_settings[2],
                    callback=self.on_post_slider,
                    user_data=2
                )
                dpg.add_slider_float(
                    label="Saturation",
                    min_value=0.0,
                    max_value=2.0,
                    default_value=self.Post_settings[3],
                    callback=self.on_post_slider,
                    user_data=3
                )
                dpg.add_slider_float(
                    label="Contrast",
                    min_value=0.5,
                    max_value=3.0,
                    default_value=self.Post_settings[4],
                    callback=self.on_post_slider,
                    user_data=4
                )
                dpg.add_slider_float(
                    label="Chromatic Aberration",
                    min_value=0.0,
                    max_value=1.0,
                    default_value=self.Post_settings[5],
                    callback=self.on_post_slider,
                    user_data=5
                )
                dpg.add_slider_float(
                    label="Highlight",
                    min_value=0.0,
                    max_value=1.0,
                    default_value=self.Post_settings[6],
                    callback=self.on_post_slider,
                    user_data=6
                )

        dpg.set_primary_window("main_ui", True)
        dpg.create_viewport(title="Controls", width=550,height=800,)
        dpg.setup_dearpygui()
        dpg.set_global_font_scale(self.default_ui_scale)
        dpg.show_viewport()

        #UI---------------------------------------------------------------------------------------------------------------UI

    def on_render(self, time: float, frame_time: float):
        
        if self.pending_hdri is not None:
            w, h, data = self.pending_hdri
            self.pending_hdri = None
            old_tex = self.hdri_tex
            self.hdri_tex = self.ctx.texture(
                (w, h),
                3,
                data,
                alignment=1
            )
            self.hdri_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self.hdri_tex.repeat_x = True
            self.hdri_tex.repeat_y = False
            self.hdri_tex.use(location=1)
            if old_tex:
                old_tex.release()
            self.frame = 0    
                
        if self.pending_window_resize is not None:
            w, h = self.pending_window_resize
            self.pending_window_resize = None
            self.wnd._window.set_size(w, h)
            return 
        
        if self.pending_resize is not None:
            width, height = self.pending_resize
            self.pending_resize = None
        
            self.ctx.finish()
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, width, height)
        
            self.resize_accumulation_buffers(width, height)
            self.frame = 0  
            
        if self.request_recompile:
            self.request_recompile = False
            try:
                fragment_shader = self.build_fragment_shader(
                    dpg.get_value(self.user_helper_editor),
                    dpg.get_value(self.user_sdf_editor),
                )
                new_program = self.ctx.program(
                    vertex_shader=self.vertex_shader_source,
                    fragment_shader=fragment_shader,
                )
                self.program.release()
                self.program = new_program
                self.frame = 0
                dpg.set_value(self.sdf_compile_log, "SDF compiled successfully :)")
            except Exception as e:
                dpg.set_value(self.sdf_compile_log, f":( Compile error:\n{e}")
                
        #--------------------------------------------

        keys = self.wnd.keys
        just_pressed = self.keys_down - self.prev_keys
        self.prev_keys = set(self.keys_down)

        if (keys.R in just_pressed
                and not keys.LEFT_CTRL in self.keys_down
        ):
            if self.iMode == 1:
                self.frame = 0
                self.iMode = 0
            else:
                self.iMode = 1


        #camera settings------------------------------------------------------------------------------------------------
        speed_a = self.cam_speed * frame_time * 0.01
        self.iCam_a = max(0.0, min(1.0, self.iCam_a))
        if keys.LEFT_CTRL in self.keys_down:

            if (keys.A in self.keys_down
                    and self.iCam_a <= 0.5):
                self.frame = 0
                self.iCam_a -= 1 * speed_a
            if (keys.D in self.keys_down
                    and self.iCam_a >= 0):
                self.frame = 0
                self.iCam_a += 1 * speed_a


        #rotation-------------------------------------------------------------------------------------------------------
        if not keys.LEFT_CTRL in self.keys_down:
            speed_yp = self.cam_speed * frame_time * 0.5
            if keys.LEFT in self.keys_down:
                self.iCam_yp[0] -= speed_yp
            if keys.RIGHT in self.keys_down:
                self.iCam_yp[0] += speed_yp
            if keys.UP in self.keys_down:
                self.iCam_yp[1] += speed_yp
            if keys.DOWN in self.keys_down:
                self.iCam_yp[1] -= speed_yp
            if (
                    keys.LEFT in self.keys_down
                    or keys.RIGHT in self.keys_down
                    or keys.UP in self.keys_down
                    or keys.DOWN in self.keys_down
            ):
                self.frame = 0
                self.sin_p = math.sin(self.iCam_yp[1])
                self.cos_p = math.cos(self.iCam_yp[1])
                self.sin_y = math.sin(self.iCam_yp[0])
                self.cos_y = math.cos(self.iCam_yp[0])

        #movement-------------------------------------------------------------------------------------------------------
        if not keys.LEFT_CTRL in self.keys_down:

            speed_pos = self.cam_speed * frame_time
            
            if keys.LEFT_SHIFT not in self.keys_down:
                speed_pos *= 0.25
                
            if (keys.SPACE in self.keys_down
            and keys.LEFT_SHIFT in self.keys_down):
                speed_pos *= 5


            if keys.W in self.keys_down:
                direction = vrotate_p([0.0, 0.0, 1.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
                for i in range(3):
                    self.iCam_pos[i] += direction[i] * speed_pos

            if keys.S in self.keys_down:
                direction = vrotate_p([0.0, 0.0, 1.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
                for i in range(3):
                    self.iCam_pos[i] -= direction[i] * speed_pos

            if keys.D in self.keys_down:
                direction = vrotate_p([1.0, 0.0, 0.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
                for i in range(3):
                    self.iCam_pos[i] += direction[i] * speed_pos

            if keys.A in self.keys_down:
                direction = vrotate_p([1.0, 0.0, 0.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
                for i in range(3):
                    self.iCam_pos[i] -= direction[i] * speed_pos

            if keys.E in self.keys_down:
                for i in range(3):
                    direction = vrotate_p([0.0, 1.0, 0.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
                    self.iCam_pos[i] += direction[i] * speed_pos

            if keys.Q in self.keys_down:
                for i in range(3):
                    direction = vrotate_p([0.0, 1.0, 0.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
                    self.iCam_pos[i] -= direction[i] * speed_pos

            if (
                    keys.W in self.keys_down
                    or keys.S in self.keys_down
                    or keys.A in self.keys_down
                    or keys.D in self.keys_down
                    or keys.E in self.keys_down
                    or keys.Q in self.keys_down
            ):
                self.frame = 0

        #to shader----------------------------------
        if "iTime" in self.program:
            self.program["iTime"].value = time
        if "iCam_Pos" in self.program:
            self.program["iCam_Pos"].value = tuple(self.iCam_pos)
        if "iCam_yp" in self.program:
            self.program["iCam_yp"].value = tuple(self.iCam_yp)
        if "iMode" in self.program:
            self.program["iMode"].value = self.iMode
        if "iCam_a" in self.program:
            self.program["iCam_a"].value = self.iCam_a

        if "World_settings" in self.program:
            self.program["World_settings"].value = tuple(float(x) for x in self.World_settings)
        if "SET" in self.program:
            self.program["SET"].value = tuple(float(x) for x in self.SET)
        if "Render_settings" in self.program:
            self.program["Render_settings"].value = tuple(float(x) for x in self.Render_settings)
        if "Post_settings" in self.post_program:
            self.post_program["Post_settings"].value = tuple(float(x) for x in self.Post_settings)

        w = self.wnd.buffer_width
        h = self.wnd.buffer_height

        if "iResolution" in self.program:
            self.program["iResolution"].value = (float(w), float(h), 1.0)
        if "iFrame" in self.program:
            self.program["iFrame"].value = self.frame
        if "iPrevFrame" in self.program:
            self.program["iPrevFrame"].value = 0

        if self.hdri_tex: 
            self.hdri_tex.use(location=1) 
            if "HDRI" in self.program: 
                self.program["HDRI"].value = 1

        #fps-------------------------------------
        self._fps_time_accum += frame_time
        self._fps_frame_accum += 1
        if self._fps_time_accum >= 0.5:
            self._last_fps = self._fps_frame_accum / self._fps_time_accum
            self._fps_time_accum = 0.0
            self._fps_frame_accum = 0

        if self.frame == 0:
            self.fbos[self.pong].use()
            self.ctx.clear(0.0, 0.0, 0.0, 0.0)



        if self.iMode == 0:
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, w, h)

            self.program["iFrame"].value = 0

            self.quad.render(self.program)

        else:
            # --- Accumulation pass ---
            if self.frame > 0:
                self.accum_textures[self.ping].use(location=0)
                if "iPrevFrame" in self.program:
                    self.program["iPrevFrame"].value = 0


            self.fbos[self.pong].use()
            self.ctx.viewport = (0, 0, w, h)
            self.quad.render(self.program)

            self.ping, self.pong = self.pong, self.ping
            self.frame += 1

            # --- Display pass ---
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, w, h)

            self.accum_textures[self.ping].use(location=0)
            if "uAccum" in self.post_program:
                self.post_program["uAccum"].value = 0
            if "iResolution" in self.post_program:
                self.post_program["iResolution"].value = (float(w), float(h), 1.0)

            self.quad.render(self.post_program)



        self.wnd.title = (f"FPT | FPS: {self._last_fps:.1f} | Depth of field strength: {self.iCam_a:.3f} |")

        #save render---------------------
        if (
                keys.S in just_pressed
                and keys.LEFT_CTRL in self.keys_down
        ):
            self.save_screenshot()
        if self.request_save_render:
            self.save_screenshot()
            self.request_save_render = False


        dpg.render_dearpygui_frame()
if __name__ == "__main__":
    mglw.run_window_config(fractal_Path_tracer)
