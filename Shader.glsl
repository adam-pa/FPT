//Shader.glsl

vec3 cam_pos = vec3(0.0,0.0,-5);
int ni = 212;
float lod_falloff = 1000.;
float pi = 3.14159265359;
float inf = 1e20;



//structs--------------------------------------------------------structs
struct Material {
	vec3 rgb;
    float roughness;
    float specular;
    float ior;
    float specularRoughness;
    float emission;
};

struct BRDFResult {
    vec3 dr;
    vec3 rp;
    vec3 color;
};

Material defaultMaterial() {
    Material m;
	m.rgb = vec3(1.0,1.0,1.0);
    m.roughness = 0.5;
    m.specular = 0.5;
    m.ior = 1.5;
    m.specularRoughness = 0.2;
    m.emission = 0.0;
    return m;
}

//Random----------------------------------------------------------------------------------------------------------Random
float hash11(float p)
{
    p = fract(p * .1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

float HoskinsRand(vec3 p) {
    uint x = floatBitsToUint(p.x);
    uint y = floatBitsToUint(p.y);
    uint z = floatBitsToUint(p.z);
    uint n = x * 1664525u + y * 1013904223u + z * 374761393u;
    n ^= (n >> 13u);
    n *= 1274126177u;
    n ^= (n >> 16u);
    return float(n) * (1.0 / 4294967296.0);
}

vec3 Random_Vector(vec3 n,vec2 xy, float seed){
    float h1 = HoskinsRand(vec3(xy, seed * 2.0 + 0.0));
	float h2 = HoskinsRand(vec3(xy, seed * 2.0 + 1.0));


    float phi = 2.0 * pi * h1;
    float z = 2.0 * h2 - 1.0;
    float r = sqrt(1.0 - z*z);
    vec3 vec = vec3(r*cos(phi), r*sin(phi), z);
    vec = normalize(vec + n);

    return vec;
}

vec3 Random_point(float power, vec2 xy, float seed){
    float r = 2.0 * HoskinsRand( vec3( xy, hash11(seed) ) ) * pi;
    float r2 = 2.0 * HoskinsRand( vec3( hash11(seed), xy ) ) * pi;
    vec3 vec = vec3(cos(r), sin(r), 0.0);
    return vec * sqrt(r2) * power;
}

//functions----------------------------------------------------------------------------------------------------functions

vec3 Hsv2rgb(vec3 c)
{
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

vec3 Rotate(vec3 v, vec2 cam_yp){
    float yaw = cam_yp.x;
    float pitch = cam_yp.y;
    
    v = vec3(v.x, v.z*sin(pitch) + v.y*cos(pitch), v.z*cos(pitch) - v.y*sin(pitch) );
    v = vec3(v.x*cos(yaw) + v.z*sin(yaw), v.y, -v.x*sin(yaw) + v.z*cos(yaw) );
    return v;
}

float Smin( float a, float b, float k ){
    float h = clamp( 0.5+0.5*(b-a)/k, 0.0, 1.0 );
    return mix( b, a, h ) - k*h*(1.0-h);
}


vec3 Studio(vec3 dr,vec3 li, float light_size){
    float ligth = max( (dot(dr, li) - 1.)/(1 - cos(light_size)) + 1, 0.0) / light_size * 3.;
    return ligth * vec3(1.0,1.0,1.0);
}

vec3 Skybox(vec3 viewDir, vec3 li){
    viewDir = normalize(viewDir);
    float t = pow(2., viewDir.y)/2.; 
    vec3 horizonColor = mix(vec3(0.8, 0.9, 1.0), vec3(0.004, 0.048, 0.253), 0.5);
    vec3 zenithColor  = vec3(0.004, 0.048, 0.253);
    vec3 sky = mix(horizonColor, zenithColor, t);
    // Sun
    float sun = max(dot(viewDir, li), 0.0);
    sky += vec3(1.0, 1.0, 0.8) * pow(sun, 64.) * 20.;
    return sky;
}

vec3 sample_HDRI(vec3 dir){
    dir = normalize(dir);
    float u = atan(dir.z, dir.x) / (2.0 * pi) + 0.5;
    float v = acos(clamp(dir.y, -1.0, 1.0)) / pi;
    vec2 uv = vec2(u, v);
    return texture(HDRI, uv).rgb;
}

vec3 Environment(vec3 viewDir){

	vec3 env = vec3(0.0);

    vec3 ligth_dir = Rotate( vec3(0.,0.,1.),vec2(World_settings[2] * pi/180. ,World_settings[3] * pi/180.));
	vec3 hdri_dir = Rotate( viewDir,vec2(World_settings[2] * pi/180. ,0.0));

    if (World_settings[0] == 0.){env = Studio(viewDir, ligth_dir, World_settings[1]); };
    if (World_settings[0] == 1.){env = Skybox(viewDir, ligth_dir); };
    if (World_settings[0] == 2.){env = sample_HDRI(hdri_dir); };
	
	//Contrast
	return (max(env * World_settings[4], 0.0) - vec3(0.5) * World_settings[5] + vec3(0.5));
}


//object function------------------------------------------------------object function


struct SDFResult { 
    float distance;
    Material material;
};

// --------------- USER SDF --------------
{{USER_HELPERS}}
{{USER_SDF}}
// ---------------------------------------

float Object(vec3 p){
    //crash protection
    float dis = min(UserSDF(p).distance, length(p));
    return dis;
} 


//Ray marching----------------------------------------------------------------------------------------------Ray marching
vec3 Ray(vec3 dr, vec3 rp, int ni){
    
    vec3 cam_pos = rp;
    for (int i = 0; i < ni; i++){
        float o = Object(rp) * 0.9;
        rp += dr * o;
        float fog_lod = dot(cam_pos - rp, cam_pos - rp);
        float lod = mix(0.1, Render_settings[4], lod_falloff/(fog_lod + lod_falloff));
        if (o < lod) break;
    }
    return rp;
}

//Normal calculation
vec3 Normal(vec3 p){
    float e = Render_settings[2];
    vec3 n =                   
    vec3( Object(p+vec3(e, 0.0, 0.0) ) - Object(p-vec3(e, 0.0, 0.0) ),
          Object(p+vec3(0.0, e, 0.0) ) - Object(p-vec3(0.0, e, 0.0) ),
          Object(p+vec3(0.0, 0.0, e) ) - Object(p-vec3(0.0, 0.0, e) ) );
    return normalize(n);          
}


//Materials----------------------------------------------------------------------------------------------------Materials
Material Material_properties(vec3 rp){
    Material material;
    // default
	material.rgb = UserSDF(rp).material.rgb;
    material.roughness          = UserSDF(rp).material.roughness;
    material.specular           = UserSDF(rp).material.specular;
    material.ior                = UserSDF(rp).material.ior;
    material.specularRoughness  = UserSDF(rp).material.specularRoughness;
    material.emission           = UserSDF(rp).material.emission;

    return material;
}


//Rendering----------------------------------------------------------------------------------------------------Rendering

//BRDF--------------------------------------------BRDF
BRDFResult BRDF(
    vec3 dr, 
    vec3 rp,
    vec3 n,  
    float frame, 
    int i, 
    vec2 xy
){
    Material material = Material_properties(rp);
    vec3 color = material.rgb;

    //fresnel
    float ior = material.ior;
    float f0 = pow((ior- 1.0) / (ior + 1.0), 2.0);
    float cosTheta = clamp(dot(n, -dr), 0.0, 1.0);
    float fresnel = f0 + (1.0 - f0) * pow(1.0 - cosTheta, 5.0);
    
    vec3 metal = reflect(dr, n);
    vec3 diffuse = Random_Vector(n,xy, frame + float(i) * 13.37);
    vec3 specular = mix(metal, diffuse, material.specularRoughness);
    
    dr = mix(metal, diffuse, material.roughness); //metalic

    if (HoskinsRand(vec3(xy, hash11(frame + 16.89))) < fresnel * material.specular) {
        dr = specular;
        color = vec3(1.0);
    }

    //error protection
    vec3 rp_s = rp;
    rp += n * 0.002;
    if (Object(rp) < 0.002){
          rp = rp_s + n * 0.001;
    }else{rp = rp_s + n * 0.002;}


    BRDFResult result;
    result.dr = dr;
    result.rp = rp;
    result.color = color;
    return result;
}


//light simulation------------------------------------------------------light simulation
vec3 Render(vec2 xy, vec3 rp,vec2 cam_yp, float frame){
    float focal_length = 1/tan(Render_settings[3]/2. * pi/180. );

    float cam_d = length(Ray(Rotate( vec3(0.0,0.0,1.0), cam_yp), rp, 50) - rp);

    vec3 dr = normalize(vec3(xy, focal_length)) + Random_point(0.0002, xy, frame);
    dr = Rotate(dr, cam_yp);
    vec3 fp = rp + dr * cam_d; 
    rp += Rotate( Random_point( iCam_a, xy, frame ), cam_yp );
    dr = normalize(fp - rp);

    vec3 cam_pos = rp;
    
    vec3 pixellight = vec3(0.0);
    vec3 pixelcolor = vec3(1.0);
	int local_ni = ni;
    
    
    for (int i = 0; i < Render_settings[0]; i++){
        rp = Ray(dr, rp, local_ni);
		//Optimization
		local_ni = int(float(ni)/(Render_settings[5]*2. + 1.));

        Material material = Material_properties(rp);

		//light------------light
        if (length(rp - cam_pos) > 10000.0){
            pixellight += Environment(dr);
            break;
        }
        if (material.emission > 0.01){
            pixellight += material.rgb * material.emission;
            break;
        }

        vec3 n = Normal(rp);
   
        BRDFResult brdf = BRDF(dr, rp, n, frame, i, xy);
        rp = brdf.rp;
        dr = brdf.dr;
        pixelcolor *= brdf.color;
        
    }    
    return pixellight * pixelcolor;
}

//Viewport--------------------------------------------------------------------------Viewport
vec3 Viewport(vec2 xy, vec3 rp,vec2 cam_yp){
    float f = 1/tan(Render_settings[3]/2. * pi/180. );

    vec3 dr = Rotate( normalize(vec3(xy, f)), cam_yp );
    vec3 cam_pos = rp;
    rp = Ray(dr, rp, ni);
    vec3 n = Normal(rp); 
    vec3 li = normalize(vec3(1.0,0.3,0.0));

    Material material = Material_properties(rp);
    vec3 color = material.rgb;

    float diffuse = max(dot(li,n), 0.0);

    color = diffuse *color;
    if (length(rp - cam_pos) > 1000.0){ color = clamp(Environment(dr),0.,1.);}

    return pow(color, vec3(1.0/2.2));
}
//MainImage----------------------------------------------------------------------------------------------------MainImage
void mainImage(out vec4 fragColor, in vec2 fragCoord)
{

    vec2 suv = fragCoord / iResolution.xy;
    vec2 uv = suv - 0.5;
    uv.x *= iResolution.x / iResolution.y;

    vec3 cam_pos = iCam_Pos;
    vec2 cam_yp  = iCam_yp;

	//Render setings
    if (iMode == 1) {
        ni = int(Render_settings[1]);
        lod_falloff = 5000.0;
    }

	//acumulation
    vec3 accum;
    if (iMode == 1) {
        vec3 col = Render(uv, cam_pos, cam_yp, float(iFrame));

        if (iFrame == 0) {
            accum = col;
        } else {
            float a = 1.0 / float(iFrame + 1);
            accum = mix(texture(iPrevFrame, suv).rgb, col, a);
        }
    } else {
        accum = Viewport(uv, cam_pos, cam_yp);
    }

	//rfagcolor
    fragColor = vec4(accum, 1.0);
}

