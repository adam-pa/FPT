from pathlib import Path
import moderngl_window as mglw
import moderngl
import math
import sys
from PIL import Image
import dearpygui.dearpygui as dpg
import numpy as np
import time as pytime
import cv2
import textwrap
import webbrowser
import re
import ast

def resource_path(relative_path: str) -> Path:
    try:
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    except AttributeError:
        base_path = Path(__file__).parent
    return base_path / relative_path

def vrotate_p(v, sin_p, cos_p, sin_y, cos_y):
    x, y, z = v
    y2 = z * sin_p + y * cos_p
    z2 = z * cos_p - y * sin_p
    x3 = x * cos_y + z2 * sin_y
    z3 = -x * sin_y + z2 * cos_y
    return x3, y2, z3

def _help(message):
    last_item = dpg.last_item()
    with dpg.group(horizontal=True) as group:
        dpg.move_item(last_item, parent=group)
        t = dpg.add_text("(?)", color=[56, 192, 255])
        with dpg.tooltip(t):
            dpg.add_text(message)

def function_definitions_glsl(glsl_code):
    pattern = r'^\s*(?:const\s+|in\s+|out\s+|inout\s+)?\b(\w+)\s+(\w+)\s*\([^)]*\)\s*\{'
    lines = glsl_code.split('\n')
    function_names = set()
    for line in lines:
        match = re.match(pattern, line)
        if match:
            function_names.add(match.group(2))
    return function_names

def replace_user_functions(glsl_code, function_names):
    for func_name in function_names:
        pattern = r'\b' + re.escape(func_name) + r'\s*\('
        glsl_code = re.sub(pattern, f'{func_name}_user(', glsl_code)
    return glsl_code

class fpt(mglw.WindowConfig):
    gl_version = (4, 3)
    title = "Fractal Path tracer"
    window_size = (1080 , 1080)
    aspect_ratio = None
    resizable = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        #World-------------------------------------------------------------World
        self.World_settings = [0.0, #Studio/Sky
                               1.0, #Light Size
                               120.0, #rotation
                               30.0, #elevation
                               1.0, #power
                               1.0 #contrast
                               ]

        #Render-----------------------------------------------------------Render
        self.Render_settings = [5, #bounces
                                312, #ni
                                0.001, #normal quality 
                                0.0005, #min distance
                                1000., #max distance
                                0.25, #adaptive marching
                                ]

        self.Mode = 0
        self.frame = 0
        self.max_samples = 10000

        self.pending_resolution_multiplier = 1.0
        self.resolution_multiplier = 1.0
        w = int(self.wnd.buffer_width * self.resolution_multiplier)
        h = int(self.wnd.buffer_height * self.resolution_multiplier)

        self.Number_of_SET = 20
        self.SET = [0.0 for self.SET in range(self.Number_of_SET)] #settings for fractal sdf's
        self.Number_of_VSET = 20
        self.VSET = [(0.0,0.0,0.0) for self.VSET in range(self.Number_of_VSET)] #settings for fractal sdf's
        
        self.Current_number_of_colors = 3
        self.Max_number_of_colors = 20
        self.Colors = [(1.0,1.0,1.0) for self.Colors in range(self.Max_number_of_colors)]
        self.Color_weights = [1.0 for self.Color_weights in range(self.Max_number_of_colors)]

        #Camera----------------------------------------------------------Camera
        self.Camera_settings = [90.0, #fov
                                0.01, #dof
                                ]

        self.Camera_speed = 2.0
        self.Cam_pos = [0.1, 0.1, -5.0]
        self.Cam_yp = [0.,0.]

        self.sin_p = math.sin(self.Cam_yp[1])
        self.cos_p = math.cos(self.Cam_yp[1])
        self.sin_y = math.sin(self.Cam_yp[0])
        self.cos_y = math.cos(self.Cam_yp[0])

        #Post-------------------------------------------------------------Post
        self.Post_settings = [0.0, #gamma
                              1.0, #exposure
                              0.0, #brightness
                              1.0, #saturation
                              1.0, #contrast
                              0.0, #chro
                              0.0 #highlights
                              ]

        #Mouse-----------------------------------------------------------Mouse
        self.prev_keys = set()
        self.keys_down = set()

        self.mouse_pos_event_c = False
        self.current_yp = [0.,0.]
        self.current_mouse_pos = [0.5,0.5]

        self.Mouse_event = False
        self.reload_render_flag = False

        #FPS----------------------------------------------------------------FPS
        self.target_fps = 165.
        self._frame_start = pytime.perf_counter()
        self._fps_time_accum = 0.0
        self._fps_frame_accum = 0.0
        self._last_fps = 0.0

        #UI------------------------------------------------------------------UI
        self.ui_render_width, self.ui_render_height = self.wnd.size
        self.default_ui_scale = 0.3

        dpg.create_context()
        self.load_fonts()
        self.setup_ui()

        #Other------------------------------------------------------------Other
        self.pending_resize = None
        self.pending_window_resize = None
        self.hdri_tex = None
        self.pending_hdri = None
        self.request_recompile = False
        self.request_resolution_multiplier_c = False
        self.request_save_render = False
        self.save_render_path = ""

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
        uniform vec3 Resolution;
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
        if "Focus_pos" in self.program: 
            self.program["Focus_pos"].value = tuple([0.0,0.0])

        self.post_program = self.ctx.program(
            vertex_shader=self.vertex_shader_source,
            fragment_shader=post_fragment_shader,
        )
        self.hdri_tex = self.ctx.texture((1, 1), 3, data=None, dtype='f4')
        self.hdri_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.hdri_tex.use(location=1)

        self.quad = mglw.geometry.quad_2d(size=(2.0, 2.0))

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


    #render save----------------------------------------------------------------render save
    def save_render_callback(self, sender, app_data):
        if not app_data or not app_data.get("file_path_name"):
            return
        path = app_data["file_path_name"]
        self.save_render_path = path
        self.request_save_render = True

    def save_screenshot(self):
        try:
            self.ctx.finish()
            w = int(self.wnd.buffer_width * self.resolution_multiplier)
            h = int(self.wnd.buffer_height * self.resolution_multiplier)
            screenshot_tex = self.ctx.texture((w, h), components=4)
            screenshot_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    
            screenshot_fbo = self.ctx.framebuffer(
                color_attachments=[screenshot_tex]
            )

            screenshot_fbo.use()
            self.ctx.viewport = (0, 0, w, h)
            self.accum_textures[self.ping].use(location=0)

            if "uAccum" in self.post_program:
                self.post_program["uAccum"].value = 0
            if "Resolution" in self.post_program:
                self.post_program["Resolution"].value = (float(w), float(h), 1.0)

            self.post_program["Post_settings"].value = tuple(float(x) for x in self.Post_settings)

            self.quad.render(self.post_program)
    
            data = screenshot_fbo.read(components=3, alignment=1)
            screenshot_fbo.release()
            screenshot_tex.release()
            image = Image.frombytes("RGB", (w, h), data)
            image = image.transpose(Image.FLIP_TOP_BOTTOM)
    
            filename = Path(self.save_render_path)
            image.save(filename)
        except:
            dpg.show_item("Something_wrong")

    #buld shaders----------------------------------------------------------buld shaders
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
        
        user_functions = function_definitions_glsl(helper_code)
        helper_code = replace_user_functions(helper_code,user_functions)
        user_sdf_code = replace_user_functions(user_sdf_code,user_functions)

        base_code = base_code.replace("{{USER_HELPERS}}", helper_code)
        base_code = base_code.replace("{{USER_SDF}}", user_sdf_code)


        return f"""
        #version 430 core
        out vec4 fragColor;
    
        uniform vec3 Resolution;
        uniform float Time;
        uniform int Frame;
        uniform vec3 Cam_Pos;
        uniform vec2 Cam_yp;
        uniform float Cam_a;
        uniform int Mode;
        uniform vec2 Focus_pos;
        
        uniform sampler2D PrevFrame;
        uniform sampler2D HDRI;
        
        uniform float Camera_settings[2];
        uniform float World_settings[6];
        uniform float SET[20];
        uniform vec3  VSET[20];
        uniform float Render_settings[6];
        
        uniform vec3 Gradient_colors[20];
        uniform float Gradient_color_weights[20];
        uniform int Gradient_number_of_colors; 
            
        {base_code}
    
        void main()
        {{
            mainImage(fragColor, gl_FragCoord.xy);
        }}
        """

    #resolution-----------------------------------------------------------resolution
    def on_resize(self, width: int, height: int):
        self.resize_accumulation_buffers(width, height)

        self.ui_render_width = width
        self.ui_render_height = height

        dpg.set_value("render_width_input", width)
        dpg.set_value("render_height_input", height)

    def resize_accumulation_buffers(self, width, height):
        w = max(int(width * self.resolution_multiplier),1)
        h = max(int(height * self.resolution_multiplier),1)
        if not hasattr(self, "accum_textures"):
            return

        self.ctx.finish()

        for tex in self.accum_textures:
            tex.release()
        for fbo in self.fbos:
            fbo.release()

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

        for fbo in self.fbos:
            fbo.use()
            fbo.clear(0.0, 0.0, 0.0, 0.0)

        self.ping = 0
        self.pong = 1
        self.renderer_reload()

    def apply_render_resolution(self):
        w = max(100, int(self.ui_render_width))
        h = max(100, int(self.ui_render_height))
        self.pending_window_resize = (w, h)
        self.request_resolution_multiplier_c = True


    #settings-----------------------------------------------------------------settings
                        
    def on_SET_c(self, sender, value, user_data):
        self.SET[user_data] = float(value)
        self.renderer_reload()
    def on_VSET_c(self, sender, value, user_data):
        self.VSET[user_data] = (value[0], value[1], value[2])
        self.renderer_reload()    
    def on_world_env_c(self, sender, app_data):
        if app_data == "Studio":
            self.World_settings[0] = 0
        elif app_data == "Sky":
            self.World_settings[0] = 1
        elif app_data == "HDRI":
            self.World_settings[0] = 2
        self.renderer_reload()

    def on_camera_speed_c(self, sender, value):
        self.Camera_speed = float(value)
    def on_world_c(self, sender, value, user_data):
        self.World_settings[user_data] = float(value)
        self.renderer_reload()
    def on_render_c(self, sender, value, user_data):
        self.Render_settings[user_data] = float(value)
        self.renderer_reload()
    def on_camera_c(self, sender, value, user_data):
        self.Camera_settings[user_data] = float(value)
        self.renderer_reload()
    def on_fpsCap_c(self, sender, value):
        self.target_fps = float(value)
    def on_max_samples_c(self, sender, value):
        self.max_samples = int(value)
        self.renderer_reload()
    def on_resolution_multiplier_c(self, sender, value):
        self.pending_resolution_multiplier = float(value)

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


    #post------------------------------------------------------------------post
    def on_gamma_change(self, sender, app_data):
        if app_data == "SRGB": self.Post_settings[0] = 0
        if app_data == "REC.709": self.Post_settings[0] = 1
        if app_data == "DCI-P3": self.Post_settings[0] = 2
        if app_data == "ACES": self.Post_settings[0] = 3
        if app_data == "RAW": self.Post_settings[0] = 4
    def on_post_c(self, sender, value, user_data):
        self.Post_settings[user_data] = float(value)


    #files-----------------------------------------------------------------files

    def load_hdri_callback(self, sender, app_data):
        try:
            if not app_data or not app_data.get("file_path_name"):
                return
            path = app_data["file_path_name"]
            img = cv2.imread(path, flags=cv2.IMREAD_UNCHANGED)
            if img is None:
                raise FileNotFoundError("OpenCV could not read the file.")

            if img.ndim == 3 and img.shape[2] >= 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
            if img.ndim == 2:
                img = np.stack([img] * 3, axis=-1)
    
            if img.shape[2] > 3:
                img = img[:, :, :3]
    
            if img.dtype == np.uint8:
                img = img.astype(np.float32) / 255.0
            else:
                img = img.astype(np.float32)
    
            h, w, _ = img.shape
            data = img.tobytes() 
            self.pending_hdri = (w, h, data)

        except Exception as e:
            dpg.show_item("Something_wrong")

    def sdf_write(self,path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "SDF:\n"
                "{\n"
            )
            f.write(textwrap.indent(dpg.get_value("user_sdf_editor"), '\t') + "\n")
            f.write(
                "}\n"
                "Helper Functions:\n"
                "{\n"
            )
            f.write(textwrap.indent(dpg.get_value("user_helper_editor"), '\t') + "\n")
            f.write(
                "}\n"
                "SDF Settings:\n"
                "{\n"
            )
            for i in range(self.Number_of_SET):
                f.write("\t" + dpg.get_value(f"SET_Name[{i}]"))
                f.write("\n")
                f.write("\t" + str(dpg.get_value(f"SET[{i}]")) )
                f.write("\n")
            f.write("}\n")
            f.write("{\n")
            for i in range(self.Number_of_SET):
                f.write("\t" + dpg.get_value(f"VSET_Name[{i}]"))
                f.write("\n")
                VSET = dpg.get_value(f"VSET[{i}]")
                f.write("\t" + str([VSET[0], VSET[1], VSET[2]]) )
                f.write("\n")
            f.write("}\n")
    def sdf_read(self,path):
        sdf = ""
        helper = ""
        mode = 0
        read_stop = False
        SET_i = 0
        VSET_i = 0        
        with open(path) as f:
            while True:
        
                line = f.readline()
                if not line:
                    break
        
                if line == "{\n":
                    read_stop = False
                    mode += 1
                    continue
        
                if line == "}\n":
                    read_stop = True
                    continue
        
                if mode == 1 and not read_stop:
                    sdf += line.replace("\t", "", 1)
        
                elif mode == 2 and not read_stop:
                    helper += line.replace("\t", "", 1)
        
                elif mode == 3 and not read_stop:
                    dpg.set_value(f"SET_Name[{SET_i}]", line.strip())
                    line = next(f, None)
                    if line:
                        SET = float(line.strip())
                        dpg.set_value(f"SET[{SET_i}]",  SET)
                        self.SET[SET_i] = SET
                    SET_i += 1
        
                elif mode == 4 and not read_stop:
                    dpg.set_value(f"VSET_Name[{VSET_i}]", line.strip())
                    line = next(f, None)
                    if line:
                        VSET = ast.literal_eval(line.strip())
                        dpg.set_value(f"VSET[{VSET_i}]",  VSET )
                        self.VSET[VSET_i] =  VSET
                    VSET_i += 1
        
            dpg.set_value("user_sdf_editor", sdf)
            dpg.set_value("user_helper_editor", helper)
            self.recompile()

    def sdf_save_callback(self, sender, app_data):
        try:
            if not app_data or not app_data.get("file_path_name"):
                return
            path = app_data["file_path_name"]
            self.sdf_write(path)
        except:
            dpg.show_item("Something_wrong")
    def sdf_open_callback(self, sender, app_data):
        try:
            if not app_data or not app_data.get("file_path_name"):
                return
            path = app_data["file_path_name"]
            self.sdf_read(path)
        except:
            dpg.show_item("Something_wrong")
            
    def sdf_open_from_button(self, sender, app_data, user_data):
        try:
            self.sdf_read(user_data)
            dpg.hide_item("Fractals")
        except:
            dpg.show_item("Something_wrong")

            
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
    #render functions-------------------------------------------------------------------------------render functions
    def renderer_reload(self):
        self.reload_render_flag = True
    def render_call(self, sender):
        if self.Mode == 0:
            dpg.set_item_label("render_call","Stop Rendering")
            self.renderer_reload()
            self.Mode = 1
        else:
            dpg.set_item_label("render_call","Start Rendering")
            self.renderer_reload()
            self.Mode = 0

    def stop_rendering(self):
        render_save = dpg.get_item_configuration("render_save_file_dialog").get("show")
        sdf_save =  dpg.get_item_configuration("sdf_save_file_dialog").get("show")
        sdf_open =  dpg.get_item_configuration("sdf_open_file_dialog").get("show")
        hdri_open = dpg.get_item_configuration("hdri_file_dialog").get("show")
        viewport_save =  dpg.get_item_configuration("Viewport_save").get("show")
        something_wrong =  dpg.get_item_configuration("Something_wrong").get("show")
        
        if (render_save 
            or sdf_save
            or sdf_open            
            or hdri_open            
            or viewport_save
            or something_wrong
            or not (self.frame < self.max_samples)
            ):
            return True
        else:
            return False
 
    #gradient creator-----------------------------------------------------------------------------------gradient creator
    def add_color(self):
        if self.Current_number_of_colors < self.Max_number_of_colors:
            self.Current_number_of_colors += 1
            dpg.delete_item("Colors",children_only=True)
            for i in range(self.Current_number_of_colors):
                col = (self.Colors[i][0] * 255,self.Colors[i][1] * 255,self.Colors[i][2] * 255,255)
                weight = self.Color_weights[i]
                with dpg.group(horizontal=True,parent="Colors"):
                    dpg.add_color_edit(default_value=col,
                                       tag=f"Color[{i}]",
                                       no_inputs=True,
                                       no_alpha=True,
                                       user_data=i,
                                       callback=self.on_color_c)

                    dpg.add_drag_float(default_value=weight,
                                       min_value=0,
                                       max_value=1e10,
                                       speed=0.005,
                                       tag=f"Color_weight[{i}]",
                                       label="Weight", 
                                       user_data=i,
                                       callback=self.on_color_weight_c)
            self.renderer_reload()
                    
    def remove_last_color(self):
        if self.Current_number_of_colors > 0:
            self.Current_number_of_colors -= 1
            dpg.delete_item(f"Color[{self.Current_number_of_colors}]")
            dpg.delete_item(f"Color_weight[{self.Current_number_of_colors}]")
            self.renderer_reload()

    def on_color_c(self, sender, value, user_data):
        self.Colors[user_data] = (value[0],value[1],value[2])
        self.renderer_reload()
    def on_color_weight_c(self, sender, value, user_data):
        self.Color_weights[user_data] = value
        self.renderer_reload()
        #UI---------------------------------------------------------------------------------------------------------------UI

    def setup_ui(self):

        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 1)

        with dpg.theme() as important_label_theme:
            with dpg.theme_component(dpg.mvAll): 
                dpg.add_theme_color(dpg.mvThemeCol_Border, (34, 83, 118))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 1)
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize,2)

        with dpg.file_dialog(
                directory_selector=False,
                show=False,
                callback=self.load_hdri_callback,
                tag="hdri_file_dialog",
                width=500,
                height=400):
            dpg.add_file_extension(".hdr", color=(56, 192, 255, 255), custom_text="HDRI (*.hdr)")


        with dpg.file_dialog(
                directory_selector=False,
                show=False,
                callback=self.sdf_open_callback,
                tag="sdf_open_file_dialog",
                width=500,
                height=400):
            dpg.add_file_extension(".fpt", color=(56, 192, 255, 255), custom_text="FPT (*.fpt)")


        with dpg.file_dialog(
                directory_selector=False,
                show=False,
                callback=self.sdf_save_callback,
                tag="sdf_save_file_dialog",
                width=500,
                height=400):
            dpg.add_file_extension(".fpt", color=(56, 192, 255, 255), custom_text="FPT (*.fpt)")


        with dpg.file_dialog(
                directory_selector=False,
                show=False,
                callback=self.save_render_callback,
                tag="render_save_file_dialog",
                width=500,
                height=400):
            dpg.add_file_extension(".png", color=(56, 192, 255, 255), custom_text="PNG (*.png)")

        with dpg.window(label="Alert", modal=True, show=False, tag="Viewport_save"):
            dpg.add_text("You can't save renders while you're in the viewport!\n"
                         "press 'Start Rendering' to start rendering")

        with dpg.window(label="Alert", modal=True, show=False, tag="Something_wrong"):
            dpg.add_text("Something went wrong!")

        with dpg.texture_registry(show=False):
            width, height, channels, data = dpg.load_image("Fractals/Tree_Fractal.png")
            dpg.add_static_texture(width=width, height=height, default_value=data, tag="Tree_Fractal_img")
            width, height, channels, data = dpg.load_image("Fractals/Ball_Fractal.png")
            dpg.add_static_texture(width=width, height=height, default_value=data, tag="Ball_Fractal_img")
            width, height, channels, data = dpg.load_image("Fractals/IFS_Fractal.png")
            dpg.add_static_texture(width=width, height=height, default_value=data, tag="IFS_Fractal_img") 
            width, height, channels, data = dpg.load_image("Fractals/Tower_Fractal.png")
            dpg.add_static_texture(width=width, height=height, default_value=data, tag="Tower_Fractal_img")
            width, height, channels, data = dpg.load_image("Fractals/Cage_Fractal.png")
            dpg.add_static_texture(width=width, height=height, default_value=data, tag="Cage_Fractal_img")
            width, height, channels, data = dpg.load_image("Fractals/Mandelbox_Fractal.png")
            dpg.add_static_texture(width=width, height=height, default_value=data, tag="Mandelbox_Fractal_img")

        with dpg.window(
                label="Fractals",
                modal=True,
                show=False,
                tag="Fractals",
                no_title_bar=False,
                width=250,
                height=400,
        ):
            dpg.add_image_button(
                texture_tag="Tree_Fractal_img",
                callback=self.sdf_open_from_button,
                user_data="Fractals/Tree_Fractal.fpt"
            )
            dpg.add_image_button( 
                texture_tag="Ball_Fractal_img",
                callback=self.sdf_open_from_button,
                user_data="Fractals/Ball_Fractal.fpt"
            )
            dpg.add_image_button(
                texture_tag="IFS_Fractal_img",
                callback=self.sdf_open_from_button,
                user_data="Fractals/IFS_Fractal.fpt"
            )
            dpg.add_image_button(
                texture_tag="Tower_Fractal_img",
                callback=self.sdf_open_from_button,
                user_data="Fractals/Tower_Fractal.fpt" 
            )
            dpg.add_image_button(
                texture_tag="Cage_Fractal_img",
                callback=self.sdf_open_from_button,
                user_data="Fractals/Cage_Fractal.fpt" 
            )
            dpg.add_image_button(
                texture_tag="Mandelbox_Fractal_img",
                callback=self.sdf_open_from_button,
                user_data="Fractals/Mandelbox_Fractal.fpt"
            )
            
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
                        label=" ? ",
                        callback=lambda:webbrowser.open("https://github.com/adam-pa/FPT/wiki")
                    )

                    dpg.add_spacer(width=5)

                    dpg.add_text("UI scale")

                    dpg.add_combo(
                        items=["70%", "100%", "130%", "160%", "200%"],
                        default_value="100%",
                        width=100,
                        callback=self.set_ui_scale
                    )
                    dpg.add_button(
                        label="Save Render!",
                        callback=lambda: dpg.show_item("render_save_file_dialog")
                    )
                    dpg.add_button(
                        label="Start Rendering",
                        tag="render_call",
                        callback=self.render_call,
                    )
                    dpg.bind_item_theme("render_call", important_label_theme)
        

            dpg.add_separator()
            with dpg.collapsing_header(label="SDF Editor", default_open=False):

                with dpg.group(horizontal=True):
                    dpg.add_button(label="SDF Save", callback=lambda: dpg.show_item("sdf_save_file_dialog"))
                    dpg.add_button(label="SDF Open", callback=lambda: dpg.show_item("sdf_open_file_dialog"))
                    a = dpg.add_button(label="Fractals!", callback=lambda: dpg.show_item("Fractals"))
                    dpg.bind_item_theme(a, important_label_theme)
                    
                with dpg.child_window(
                        height=440,
                        border=True,
                        resizable_y=True

                ):
                    with dpg.tab_bar():
                        with dpg.tab(label="SDF"):
                            self.user_sdf_editor = dpg.add_input_text(
                                label="",
                                multiline=True,
                                height=-1,
                                width= -1,
                                tab_input=True,
                                tag="user_sdf_editor",
                                default_value=(
                                    "float Sphere = Sphere_SDF(p, 1.);\n"
                                    "sdf = Sphere;\n"
                                    "\n"
                                    "\n"
                                    "//Material Settings:\n"
                                    "material.rgb = vec3(1.);\n"
                                    "material.roughness = 1.0;\n"
                                    "material.specular = 0.0;\n"
                                    "material.translucency = 0.0;\n"
                                    "material.ior = 1.5;\n"
                                    "material.emission = 0.0;\n"
    
                                )
                            )
                        with dpg.tab(label="Helper Functions"):
                            self.user_helper_editor = dpg.add_input_text(
                                label="",
                                multiline=True,
                                height=-1,
                                width= -1,
                                tab_input=True,
                                tag="user_helper_editor",
                                default_value=(
                                    "float Sphere_SDF(vec3 p, float r){\n"
                                    "   return length(p)-r;\n"
                                    "}\n"
                                )
                            )
                        with dpg.tab(
                                label="SDF Settings",
                        ):
                            with dpg.tab_bar():
                                
                                with dpg.tab(label="float"):
                                    with dpg.table(header_row=True, resizable=True):
                                        dpg.add_table_column(label="In Code", init_width_or_weight=1.5)
                                        dpg.add_table_column(label="Value", init_width_or_weight=5)
                                        dpg.add_table_column(label="Name", init_width_or_weight=4)
        
                                        for i in range(self.Number_of_SET): 
                                            with dpg.table_row():
                                                for j in range(3):
                                                    if j == 0:
                                                        dpg.add_text(f"SET[{i}]")
                                                    if j == 1:
                                                        dpg.add_drag_float(
                                                            label="",
                                                            width=-1,
                                                            max_value=1e10,
                                                            min_value=-1e10,
                                                            default_value=0.0,
                                                            speed=0.005,
                                                            callback=self.on_SET_c,
                                                            user_data=i,
                                                            tag=f"SET[{i}]"
                                                        )
                                                    if j == 2:
                                                        dpg.add_input_text(
                                                            default_value="",width=-1,tag=f"SET_Name[{i}]")
                                                        
                                with dpg.tab(label="vec3"):
                                    with dpg.table(header_row=True, resizable=True):
                                        dpg.add_table_column(label="In Code", init_width_or_weight=1.5)
                                        dpg.add_table_column(label="Value", init_width_or_weight=5)
                                        dpg.add_table_column(label="Name", init_width_or_weight=4)

                                        for i in range(self.Number_of_VSET):
                                            with dpg.table_row():
                                                for j in range(3):
                                                    if j == 0:
                                                        dpg.add_text(f"VSET[{i}]")
                                                    if j == 1:
                                                        dpg.add_drag_floatx(
                                                            size=3,
                                                            label="",
                                                            width=-1,
                                                            max_value=1e10,
                                                            min_value=-1e10,
                                                            callback=self.on_VSET_c,
                                                            speed=0.005,
                                                            user_data=i,
                                                            tag=f"VSET[{i}]"
                                                        )
                                                    if j == 2:
                                                        dpg.add_input_text(
                                                            default_value="",width=-1,tag=f"VSET_Name[{i}]")
                        with dpg.tab(
                                label="Gradient Creator",
                        ):
                            dpg.add_text("To use your gradient:\n"
                                         "material.rgb = Gradient('your orbit trap')\n"
                                         )
                            dpg.add_button(label="Example",user_data="Fractals/Gradient_Example.fpt", callback=self.sdf_open_from_button)
                            dpg.add_spacer(height=10)
                            with dpg.group(horizontal=True): 
                                dpg.add_button(label="Add Color", callback= self.add_color) 
                                dpg.add_button(label="Remove Last Color", callback= self.remove_last_color)
                                
                            with dpg.group(tag="Colors"):
                                for i in range(self.Current_number_of_colors):
                                    col = (self.Colors[i][0] * 255,self.Colors[i][1] * 255,self.Colors[i][2] * 255,255)
                                    weight = self.Color_weights[i]
                                    with dpg.group(horizontal=True):
                                        dpg.add_color_edit(default_value=col,
                                                           tag=f"Color[{i}]",
                                                           no_inputs=True,
                                                           no_alpha=True,
                                                           user_data=i,
                                                           callback=self.on_color_c)
                                        
                                        dpg.add_drag_float(default_value=weight,
                                                           min_value=0,
                                                           max_value=1e10,
                                                           speed=0.005,
                                                           tag=f"Color_weight[{i}]",
                                                           label="Weight",
                                                           user_data=i,
                                                           callback=self.on_color_weight_c)
                                                                       

                dpg.add_separator()
                dpg.add_button(
                    label="Recompile SDF",
                    callback=self.recompile
                )
                self.sdf_compile_log = dpg.add_text("")

            dpg.add_separator()
            with dpg.collapsing_header(label="Camera Settings", default_open=False):
                dpg.add_slider_float(
                    label="Fov",
                    min_value=0.0,
                    max_value=180,
                    default_value=self.Camera_settings[0],
                    callback=self.on_camera_c,
                    user_data=0,
                )

                dpg.add_slider_float(
                    label="Depth of field",
                    min_value=0.0,
                    max_value=0.2,
                    default_value=self.Camera_settings[1],
                    callback=self.on_camera_c,
                    user_data=1,
                )
                dpg.add_input_float(
                    label="Camera Speed",
                    default_value=self.Camera_speed,
                    callback=self.on_camera_speed_c,
                )

            dpg.add_separator()
            with dpg.collapsing_header(label="Render Settings", default_open=False):

                dpg.add_input_int(
                    label="Bounces",
                    default_value=int(self.Render_settings[0]),
                    callback=self.on_render_c,
                    user_data=0
                )
                dpg.add_input_int(
                    label="Marching Steps",
                    default_value=int(self.Render_settings[1]),
                    callback=self.on_render_c,
                    user_data=1
                )
                _help(
                    "Ray accuracy,\n"
                    "bigger values make rays more accurate\n"
                )
                dpg.add_input_float(
                    label="Normal Epsilon",
                    default_value=self.Render_settings[2],
                    callback=self.on_render_c,
                    user_data=2,
                    step=0.00005,
                    format="%.6f"
                )
                _help(
                    "Normal vector accuracy,\n"
                    "smaller values make normals more accurate\n"
                )
                dpg.add_input_float(
                    label="Min Distance",
                    default_value=self.Render_settings[3],
                    callback=self.on_render_c,
                    user_data=3,
                    step=0.00005,
                    format="%.6f"
                )
                dpg.add_input_float(
                    label="Max Distance",
                    default_value=self.Render_settings[4],
                    callback=self.on_render_c,
                    user_data=4,
                    step=10.,
                )
                dpg.add_slider_float(
                    label="Adaptive Marching",
                    default_value=self.Render_settings[5],
                    min_value=0,
                    max_value=1,
                    callback=self.on_render_c,
                    user_data=5
                )

                dpg.add_slider_float(
                    label="Max FPS",
                    default_value=165.,
                    min_value=60,
                    max_value=250,
                    callback=self.on_fpsCap_c,
                )

                dpg.add_input_int(
                    label="Max Samples",
                    default_value=self.max_samples,
                    callback=self.on_max_samples_c,
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

                dpg.add_input_float(
                    label="Resolution Multiplier",
                    default_value=self.resolution_multiplier,
                    callback=self.on_resolution_multiplier_c,
                    width=180,
                    step=0.1,
                    format="%.1f"
                )
                _help(
                    "By increasing this value\n"
                    "you can keep your current window size but\n"
                    "render at for example two times your resolution\n"
                )

                dpg.add_button(
                    label="Apply Resolution",
                    width=280,
                    callback=lambda: self.apply_render_resolution()
                )

            dpg.add_separator()
            with dpg.collapsing_header(label="World Controls", default_open=False):

                dpg.add_combo(
                    label="Environment",
                    items=["Studio", "Sky", "HDRI"],
                    default_value="Studio",
                    callback=self.on_world_env_c
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
                    callback=self.on_world_c,
                    user_data=1
                )
                dpg.add_slider_float(
                    label="Rotation",
                    min_value=0.0,
                    max_value=360,
                    default_value=self.World_settings[2],
                    callback=self.on_world_c,
                    user_data=2
                )

                dpg.add_slider_float(
                    label="Light Elevation",
                    min_value=0.0,
                    max_value=360,
                    default_value=self.World_settings[3],
                    callback=self.on_world_c,
                    user_data=3
                )
                dpg.add_input_float(
                    label="Power",
                    default_value=self.World_settings[4],
                    callback=self.on_world_c,
                    user_data=4
                )
                dpg.add_input_float(
                    label="Contrast",
                    default_value=self.World_settings[5],
                    callback=self.on_world_c,
                    user_data=5,
                    step = 0.01
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
                    callback=self.on_post_c,
                    user_data=1
                )
                dpg.add_slider_float(
                    label="Brightness",
                    min_value=-1.0,
                    max_value=1.0,
                    default_value=self.Post_settings[2],
                    callback=self.on_post_c,
                    user_data=2
                )
                dpg.add_slider_float(
                    label="Saturation",
                    min_value=0.0,
                    max_value=2.0,
                    default_value=self.Post_settings[3],
                    callback=self.on_post_c,
                    user_data=3
                )
                dpg.add_slider_float(
                    label="Contrast",
                    min_value=0.5,
                    max_value=3.0,
                    default_value=self.Post_settings[4],
                    callback=self.on_post_c,
                    user_data=4
                )
                dpg.add_slider_float(
                    label="Chromatic Aberration",
                    min_value=0.0,
                    max_value=1.0,
                    default_value=self.Post_settings[5],
                    callback=self.on_post_c,
                    user_data=5
                )
                dpg.add_slider_float(
                    label="Highlight",
                    min_value=0.0,
                    max_value=1.0,
                    default_value=self.Post_settings[6],
                    callback=self.on_post_c,
                    user_data=6
                )

        dpg.set_primary_window("main_ui", True)
        dpg.create_viewport(title="Controls", width=550,height=800,)
        dpg.setup_dearpygui()
        dpg.bind_theme(global_theme)
        dpg.set_global_font_scale(self.default_ui_scale)
        dpg.show_viewport()

    #key/mouse-------------------------------------------------------------------------------key/mouse
    def on_key_event(self, key, action, modifiers):
        keys = self.wnd.keys
        if action == keys.ACTION_PRESS:
            self.keys_down.add(key)
        elif action == keys.ACTION_RELEASE:
            self.keys_down.discard(key)


    def on_mouse_press_event(self, x, y, button):
        w = self.wnd.buffer_width
        h = self.wnd.buffer_height
        x /= w
        y /= h
        x -= 0.5
        y -= 0.5
        x *= w/h
        if button == 1:
            self.renderer_reload()
            if "Focus_pos" in self.program:
                self.program["Focus_pos"].value = tuple([x,-y])

        if button == 2:
            self.mouse_pos_event_c = True
            self.current_yp = self.Cam_yp.copy()
            self.current_mouse_pos = [x,y].copy()

    def on_mouse_release_event(self, x: int, y: int, button: int):
        if button == 2:
            self.mouse_pos_event_c = False

    def on_mouse_drag_event(self, x, y, dx, dy):
        w = self.wnd.buffer_width
        h = self.wnd.buffer_height
        x /= w
        y /= h
        x -= 0.5
        y -= 0.5
        x *= w/h
        if self.mouse_pos_event_c == True:
            self.renderer_reload()
            self.sin_p = math.sin(self.Cam_yp[1]) 
            self.cos_p = math.cos(self.Cam_yp[1])
            self.sin_y = math.sin(self.Cam_yp[0])
            self.cos_y = math.cos(self.Cam_yp[0])
            self.Cam_yp[0] = self.current_yp[0] + (x-self.current_mouse_pos[0])*3.
            self.Cam_yp[1] = self.current_yp[1] + -(y-self.current_mouse_pos[1])*3.


    #render-------------------------------------------------------------------------------render   
    def on_render(self, time: float, frame_time: float):

        if self.request_resolution_multiplier_c:
            self.resolution_multiplier = self.pending_resolution_multiplier
            self.request_resolution_multiplier_c = False
            self.renderer_reload()

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
            self.renderer_reload()

        w = int(self.wnd.buffer_width * self.resolution_multiplier)
        h = int(self.wnd.buffer_height * self.resolution_multiplier)

        o_w = self.wnd.buffer_width
        o_h = self.wnd.buffer_height

        if self.reload_render_flag:
            self.frame = 0
            self.fbos[self.pong].use()
            self.ctx.clear(0.0, 0.0, 0.0, 0.0)
            self.reload_render_flag = False

        if self.pending_hdri is not None:
            w, h, data = self.pending_hdri
            self.pending_hdri = None
            old_tex = self.hdri_tex

            self.hdri_tex = self.ctx.texture(
                (w, h),
                components=3,
                data=data,
                dtype='f4',
                alignment=1
            )
            self.hdri_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self.hdri_tex.repeat_x = True
            self.hdri_tex.repeat_y = False
            self.hdri_tex.use(location=1)
            if old_tex:
                old_tex.release()
            self.renderer_reload()

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
                self.renderer_reload()
                dpg.set_value(self.sdf_compile_log, "SDF compiled successfully :)")
            except Exception as e:
                dpg.set_value(self.sdf_compile_log, f":( Compile error:\n{e}")

        #--------------------------------------------
        keys = self.wnd.keys
        just_pressed = self.keys_down - self.prev_keys
        self.prev_keys = set(self.keys_down)

        #rotation-------------------------------------------------------------------------------------------------------
        speed_yp = self.Camera_speed * frame_time * 0.5

        if keys.LEFT in self.keys_down:
            self.Cam_yp[0] -= speed_yp
        if keys.RIGHT in self.keys_down:
            self.Cam_yp[0] += speed_yp
        if keys.UP in self.keys_down:
            self.Cam_yp[1] += speed_yp
        if keys.DOWN in self.keys_down:
            self.Cam_yp[1] -= speed_yp
        if (
                keys.LEFT in self.keys_down
                or keys.RIGHT in self.keys_down
                or keys.UP in self.keys_down
                or keys.DOWN in self.keys_down
        ):
            self.renderer_reload()
            self.sin_p = math.sin(self.Cam_yp[1])
            self.cos_p = math.cos(self.Cam_yp[1])
            self.sin_y = math.sin(self.Cam_yp[0])
            self.cos_y = math.cos(self.Cam_yp[0])

        #movement-------------------------------------------------------------------------------------------------------
        speed_pos = self.Camera_speed * frame_time * 0.25

        if keys.LEFT_SHIFT in self.keys_down:
            speed_pos *= 5

        if (keys.SPACE in self.keys_down
                and keys.LEFT_SHIFT in self.keys_down):
            speed_pos *= 5


        if keys.W in self.keys_down:
            direction = vrotate_p([0.0, 0.0, 1.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
            for i in range(3):
                self.Cam_pos[i] += direction[i] * speed_pos

        if keys.S in self.keys_down:
            direction = vrotate_p([0.0, 0.0, 1.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
            for i in range(3):
                self.Cam_pos[i] -= direction[i] * speed_pos

        if keys.D in self.keys_down:
            direction = vrotate_p([1.0, 0.0, 0.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
            for i in range(3):
                self.Cam_pos[i] += direction[i] * speed_pos

        if keys.A in self.keys_down:
            direction = vrotate_p([1.0, 0.0, 0.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
            for i in range(3):
                self.Cam_pos[i] -= direction[i] * speed_pos

        if keys.E in self.keys_down:
            direction = vrotate_p([0.0, 1.0, 0.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
            for i in range(3):
                self.Cam_pos[i] += direction[i] * speed_pos

        if keys.Q in self.keys_down:
            direction = vrotate_p([0.0, 1.0, 0.0], self.sin_p , self.cos_p, self.sin_y, self.cos_y)
            for i in range(3):
                self.Cam_pos[i] -= direction[i] * speed_pos

        if (
                keys.W in self.keys_down
                or keys.S in self.keys_down
                or keys.A in self.keys_down
                or keys.D in self.keys_down
                or keys.E in self.keys_down
                or keys.Q in self.keys_down
        ):
            self.renderer_reload()

        #to shader----------------------------------
        if "Time" in self.program:
            self.program["Time"].value = time
        if "Cam_Pos" in self.program:
            self.program["Cam_Pos"].value = tuple(self.Cam_pos)
        if "Cam_yp" in self.program:
            self.program["Cam_yp"].value = tuple(self.Cam_yp)
        if "Mode" in self.program:
            self.program["Mode"].value = self.Mode

        if "Camera_settings" in self.program:
            self.program["Camera_settings"].value = tuple(self.Camera_settings)
        if "World_settings" in self.program:
            self.program["World_settings"].value = tuple(self.World_settings)


        if "SET" in self.program:
            self.program["SET"].value = tuple(self.SET)
        if "VSET" in self.program:
            self.program["VSET"].value = tuple(self.VSET)

        if "Gradient_colors" in self.program:
            self.program["Gradient_colors"].value = tuple(self.Colors)
        if "Gradient_color_weights" in self.program:
            self.program["Gradient_color_weights"].value = tuple(self.Color_weights)
        if "Gradient_number_of_colors" in self.program:
            self.program["Gradient_number_of_colors"].value = self.Current_number_of_colors                
                
        if "Render_settings" in self.program:
            self.program["Render_settings"].value = tuple(self.Render_settings)
        if "Post_settings" in self.post_program:
            self.post_program["Post_settings"].value = tuple(self.Post_settings)

        if "Resolution" in self.program:
            self.program["Resolution"].value = (float(w), float(h), 1.0)
        if "Frame" in self.program:
            self.program["Frame"].value = self.frame
        if "PrevFrame" in self.program:
            self.program["PrevFrame"].value = 0

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

        if self.Mode == 0:
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, o_w, o_h)
            self.program["Resolution"].value = (float(o_w), float(o_h), 1.0)
            self.program["Frame"].value = 0
            self.quad.render(self.program)

        else:
            # --- Accumulation pass ---
            if not self.reload_render_flag:
                self.accum_textures[self.ping].use(location=0)
                if "PrevFrame" in self.program:
                    self.program["PrevFrame"].value = 0
            
            if not self.stop_rendering():
                self.fbos[self.pong].use()
                self.ctx.viewport = (0, 0, w, h)

                self.program["Resolution"].value = (float(w), float(h), 1.0)

                self.quad.render(self.program)

                self.ping, self.pong = self.pong, self.ping
                self.frame += 1

            # --- Display pass ---
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, o_w, o_h)

            self.accum_textures[self.ping].use(location=0)  
            if "uAccum" in self.post_program:
                self.post_program["uAccum"].value = 0
            if "Resolution" in self.post_program:
                self.post_program["Resolution"].value = (float(o_w), float(o_h), 1.0)

            self.quad.render(self.post_program)


        #title----------------------------------------------------title

        if self.Mode == 1:
            if self.frame != self.max_samples:
                if self.stop_rendering():
                    rendering_state = "Rendering Stopped"
                else:
                    rendering_state = "Processing..."
            else:
                rendering_state = "Finished!"
        else:
            rendering_state = "Not Rendering"

        self.wnd.title = (f"FPT | FPS: {self._last_fps:.1f} | Samples: {self.frame:.0f} | {rendering_state} |")



        if self.request_save_render and self.Mode == 1:
            self.save_screenshot()
            self.request_save_render = False

        if self.request_save_render and self.Mode == 0:
            dpg.show_item("Viewport_save") 
            self.request_save_render = False

        
        #ui render---------------------
        dpg.render_dearpygui_frame()

        #fps cap---------------------
        frame_time_target = 1.0 / self.target_fps
        now = pytime.perf_counter()
        elapsed = now - self._frame_start
        if elapsed < frame_time_target:
            pytime.sleep(frame_time_target - elapsed)
            now = pytime.perf_counter()
        self._frame_start = now

if __name__ == "__main__":
    mglw.run_window_config(fpt)
