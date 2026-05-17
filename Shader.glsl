//Shader.glsl
const float pi = 3.14159265359;
const float inf = 1e20;

//structs--------------------------------------------------------structs
struct Material {
	vec3 rgb;
    float roughness;
    float specular;
    float translucency;
    float ior;
    float emission;
};

struct BRDFResult {
    vec3 dr;
    vec3 rp;
    vec3 color;
    float side;
};

Material defaultMaterial() {
    Material m;
	m.rgb = vec3(1.0,1.0,1.0);
    m.roughness = 1.0;
    m.specular = 0.0;
    m.translucency = 0.0;
    m.ior = 1.5;
    m.emission = 0.0;
    return m;
}
 

//USER function------------------------------------------------------USER function

float Smin( float a, float b, float k ){
    float h = clamp( 0.5+0.5*(b-a)/k, 0.0, 1.0 );
    return mix( b, a, h ) - k*h*(1.0-h);
}

vec3 Hsv2rgb(vec3 c){
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

vec3 Gradient(float orbit_trap){
    float c = fract(orbit_trap);

    float pos_1 = floor(c*float(Gradient_number_of_colors));
    float pos_2 = ceil(c*float(Gradient_number_of_colors));
	pos_1 = mod(pos_1,Gradient_number_of_colors);
	pos_2 = mod(pos_2,Gradient_number_of_colors);

    vec3 a = Gradient_colors[int(pos_1)];
    vec3 b = Gradient_colors[int(pos_2)];

    float wa = Gradient_color_weights[int(pos_1)];
    float wb = Gradient_color_weights[int(pos_2)];

    float k = fract(float(Gradient_number_of_colors) * c);

    vec3 final_col = ( a*wa*(1.-k) + b*wb*k ) / ( wa*(1.-k) + wb*k );

	vec3 dummy = vec3(0.0);
	for (int i = 0; i < Gradient_number_of_colors; i++){
		dummy *= Gradient_colors[i] * Gradient_color_weights[i]; 
	}

    return final_col + dummy*0.;
}  

// --------------- USER SDF --------------
struct SDFResult { 
    float distance;
    Material material;
};

{{USER_HELPERS}}
{{USER_SDF}}
// ----------------------------------------


//Random----------------------------------------------------------------------------------------------------------Random
float hash11(float p){
    p = fract(p * .1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

float HoskinsRand(vec3 p) {
	p.x = hash11(p.x);
	p.y = hash11(p.y);
	p.z = hash11(p.z);
    uint x = floatBitsToUint(p.x);
    uint y = floatBitsToUint(p.y);
    uint z = floatBitsToUint(p.z);
    uint n = x * 1664525u + y * 1013904223u + z * 374761393u; 
    n ^= (n >> 13u);
    n *= 1274126177u;
    n ^= (n >> 16u);
    return float(n) * (1.0 / 4294967296.0);
}

vec3 Random_Vector(vec3 normal, vec2 xy, float frameIndex){
 
    float h1 = HoskinsRand(vec3(xy, frameIndex * 2.0 + 0.0));
	float h2 = HoskinsRand(vec3(xy, frameIndex * 2.0 + 1.0));

    vec3 n = normalize(normal);

    vec3 uu = normalize(cross(n, vec3(0.0, 1.0, 1.0)));
    vec3 vv = cross(uu, n);

    float ra = sqrt(h2);
    float rx = ra * cos(pi * 2. * h1);
    float ry = ra * sin(pi * 2. * h1);
    float rz = sqrt(1.0 - h2);
    vec3 rr = vec3(rx * uu + ry * vv + rz * n);

    return normalize(rr);
}

vec3 Random_point(float power, vec2 xy, float seed){
    float r = 2.0 * HoskinsRand( vec3( xy, hash11(seed) ) ) * pi;
    float r2 = 2.0 * HoskinsRand( vec3( hash11(seed), xy ) ) * pi;
    vec3 vec = vec3(cos(r), sin(r), 0.0);
    return vec * sqrt(r2) * power;
}

//functions----------------------------------------------------------------------------------------------------functions

vec3 Rotate(vec3 v, vec2 cam_yp){
    float yaw = cam_yp.x;
    float pitch = cam_yp.y;
    
    v = vec3(v.x, v.z*sin(pitch) + v.y*cos(pitch), v.z*cos(pitch) - v.y*sin(pitch) );
    v = vec3(v.x*cos(yaw) + v.z*sin(yaw), v.y, -v.x*sin(yaw) + v.z*cos(yaw) );
    return v;
}

vec3 Studio(vec3 dr,vec3 li, float light_size){
    float ligth = max( (dot(dr, li) - 1.)/(1. - cos(light_size)) + 1., 0.0) / light_size * 3.;
    return ligth * vec3(1.0,1.0,1.0);
}

float Preetham(vec3 dr, vec3 sunDir){
    float T = 2.0;

    float A =  0.1787*T - 1.4630;
    float B = -0.3554*T + 0.4275;
    float C = -0.0227*T + 5.3251;
    float D =  0.1206*T - 2.5771;
    float E = -0.0670*T + 0.3703;

    float theta = acos(clamp(dr.y, -1.0, 1.0));
    float gamma = acos(clamp(dot(dr, sunDir), -1.0, 1.0));

    float term1 = 1.0 + A * exp(B / max(0.1, cos(theta)));
    float term2 = 1.0 + C * exp(D * gamma) + E * pow(cos(gamma),2.0);

    return term1 * term2;
}

vec3 Sky(vec3 dr, vec3 sunDir){
    float sky = Preetham(dr,sunDir);
    
    vec3 col = mix(vec3(0.004, 0.048, 0.253),
               vec3(0.8, 0.9, 1.0),
               sky); 
   
    float height_dr = (dr.y+1.)/2.;
    float height_sunDirr = (sunDir.y+1.)/2.;          
    
    col = mix(vec3(1.0,0.85,0.53)/4.,col * 1.2,height_dr) * height_sunDirr;
    col = (col-0.5)*1.2+0.5;
    float light_size = 0.05;
    float sun_disk = max( (dot(dr, sunDir) - 1.)/(1. - cos(light_size)) + 1., 0.0);
    sun_disk *= pow(height_dr,10.);
               
    return col * 0.8 + sun_disk*100.;
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
    if (World_settings[0] == 1.){env = Sky(viewDir, ligth_dir); };
    if (World_settings[0] == 2.){env = sample_HDRI(hdri_dir); };
	
	vec3 final_env = (max(env * World_settings[4], 0.0) - vec3(0.5) * World_settings[5] + vec3(0.5));
	final_env = max(final_env,0.0);
	return final_env;
}


//object function------------------------------------------------------object function
float Object(vec3 p){
    float dis = UserSDF(p).distance;
    return dis;
} 


//Ray marching----------------------------------------------------------------------------------------------Ray marching
vec3 Ray(vec3 dr, vec3 rp, int ni, float min_dist, float lod_falloff){
    
    vec3 cam_pos = rp;
    for (int i = 0; i < ni; i++){
        float o = abs(Object(rp)) * 0.99;
        rp += dr * o;

        float fog_lod = dot(cam_pos - rp,cam_pos - rp);
        float lod = mix(min_dist,0.1, fog_lod/lod_falloff);
		lod = mix(0.0001, lod, Render_settings[5]);

        if (UserSDF(rp).material.translucency > 0.0){lod = 0.0001;}
        if (o < lod) break;
		if (Render_settings[4] < o) break;
		
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
	material.rgb                = UserSDF(rp).material.rgb;
    material.roughness          = UserSDF(rp).material.roughness;
    material.specular           = UserSDF(rp).material.specular;
    material.translucency       = UserSDF(rp).material.translucency;
    material.ior                = UserSDF(rp).material.ior;
    material.emission           = UserSDF(rp).material.emission; 

    return material;
}


//Rendering----------------------------------------------------------------------------------------------------Rendering

//BRDF--------------------------------------------BRDF
BRDFResult BRDF(
    vec3 dr, 
    vec3 rp,
    float side,
    float frame, 
    int i, 
    vec2 xy
){
    Material material = UserSDF(rp).material;
    vec3 color = material.rgb;
    float ior = material.ior;

	vec3 n = Normal(rp);
    
    vec3 metal = reflect(dr, n);
    vec3 diffuse = Random_Vector(n,xy, frame + float(i) * 13.37);
    vec3 specular = reflect(dr, n);

    float r1 = HoskinsRand(vec3(xy, frame + float(i) * 1.37));
    float r2 = HoskinsRand(vec3(xy, frame + float(i) * 7.91));
    
    if ( r1 > material.translucency ){

        //fresnel
        float f0 = pow((ior- 1.0) / (ior + 1.0), 2.0);
        float cosTheta = clamp(dot(n, -dr), 0.0, 1.0);
        float fresnel = f0 + (1.0 - f0) * pow(1.0 - cosTheta, 5.0);

        dr = mix(metal, diffuse, material.roughness); //metalic

        if (r2 < fresnel * material.specular) {
            dr = specular;
            color = vec3(1.0);
        }

    }else{

        float eta;
        if (side == 1.0){eta = 1.0 / ior;}
        else{eta = ior; n = -n;}

        //fresnel
        float f0 = pow((ior- 1.0) / (ior + 1.0), 2.0);
        float cosTheta = clamp(dot(n, -dr), 0.0, 1.0);
        float fresnel = f0 + (1.0 - f0) * pow(1.0 - cosTheta, 5.0);

        vec3 refracted = refract(dr, n, eta);
        vec3 reflected = reflect(dr, n);

        vec3 jitterR = Random_Vector(reflected, xy, frame + float(i));
        vec3 jitterT = Random_Vector(refracted, xy, frame + float(i) + 17.0);

        reflected = normalize(mix(reflected, jitterR, material.roughness));
        refracted = normalize(mix(refracted, jitterT, material.roughness));

        if (r2 < fresnel) {
            dr = reflected;
        } else {
            dr = refracted;
            side *= -1;
            color *= (1.0 - fresnel);
        }       
    }
    rp += n * 0.001 * sign(dot(dr, n));


    BRDFResult result;
    result.dr = dr;
    result.rp = rp;
    result.color = color;
    result.side = side;
    return result;
}


//light simulation------------------------------------------------------light simulation
vec3 Render(vec2 xy){

	//camera veriables
	float frame = float(Frame);
	vec3 rp = Cam_Pos;
	vec2 cam_yp = Cam_yp; 
    float focal_length = 1/tan(Camera_settings[0]/2. * pi/180. );
    float cam_d = length(Ray(Rotate(normalize(vec3(Focus_pos, focal_length)), cam_yp), rp, 50, 0.001, 1000.) - rp);

	//camera 
	float aa_strength = .4/(min(Resolution.x,Resolution.y));
    vec3 dr = normalize(vec3(xy + Random_point(aa_strength, xy, frame).xy, focal_length));
    dr = Rotate(dr, cam_yp);
    vec3 fp = rp + dr * cam_d; 
    rp += Rotate( Random_point( Camera_settings[1] , xy, frame ), cam_yp );
    dr = normalize(fp - rp);

	int local_ni = int(Render_settings[1]);
    float side = 1;
    vec3 cam_pos = rp;

    vec3 pixellight = vec3(0.0);
    vec3 pixelcolor = vec3(1.0);    
    
    for (int i = 0; i < Render_settings[0]; i++){
        rp = Ray(dr, rp, local_ni, Render_settings[3], 5000.);
		//Optimization
		local_ni = int(Render_settings[1]/(Render_settings[5]*2. + 1.));

        Material material = UserSDF(rp).material;

		//light------------light
        if (length(rp - cam_pos) > Render_settings[4]){
            pixellight += Environment(dr);
            break;}

        if (material.emission > 0.001){
            pixellight += material.rgb * material.emission;
            break;}
   
		//BRDF--------------BRDF
        BRDFResult brdf = BRDF(dr, rp, side, frame, i, xy);
        rp = brdf.rp;
        dr = brdf.dr;
        side = brdf.side;
        pixelcolor *= brdf.color;
    }    
    return pixellight * pixelcolor;
}

//Viewport--------------------------------------------------------------------------Viewport
vec3 Viewport(vec2 xy){
	vec3 rp = Cam_Pos;
	vec2 cam_yp = Cam_yp; 

    float f = 1./tan(Camera_settings[0]/2. * pi/180. );

    vec3 dr = Rotate( normalize(vec3(xy, f)), cam_yp );
    vec3 cam_pos = rp;
    rp = Ray(dr, rp, 212, 0.001, 1000.);
    vec3 n = Normal(rp); 
    vec3 li = normalize(vec3(1.0,0.3,0.0));

    vec3 color = UserSDF(rp).material.rgb;

    float diffuse = max(dot(li,n), 0.0);

    color = diffuse *color;
    if (length(rp - cam_pos) > 1000.0){ color = clamp(Environment(dr),0.,1.);}

    return pow(color, vec3(1.0/2.2));
}
//MainImage----------------------------------------------------------------------------------------------------MainImage
void mainImage(out vec4 fragColor, in vec2 fragCoord)
{

	float fdummy = 0.0;
	for (int i = 0; i < SET.length(); i++){
		fdummy *= SET[i]; 
	}
	vec3 vdummy = vec3(0.0);
	for (int i = 0; i < VSET.length(); i++){
		vdummy *= VSET[i]; 
	}


    vec2 suv = fragCoord / Resolution.xy;
    vec2 uv = suv - 0.5;
    uv.x *= Resolution.x / Resolution.y;


	//acumulation
    vec3 accum;
    if (Mode == 1) {
        vec3 col = Render(uv);

        if (Frame == 0) {
            accum = col;
        } else {
            float a = 1.0 / float(Frame + 1);
            accum = mix(texture(PrevFrame, suv).rgb, col, a);
        }
        fragColor = vec4(accum + (vdummy*fdummy*0.), 1.0);

    }else{fragColor = vec4(Viewport(uv) + (vdummy*fdummy*0.) ,1.0);}
     
}
