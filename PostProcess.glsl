// PostProcess.glsl

//Gamma corectio------------------------------------------------------------------------------------------Gamma corectio
vec3 Gamma_srgb_exact(vec3 lin) {
    vec3 s;
    s.r = (lin.r <= 0.0031308) ? lin.r*12.92 : 1.055*pow(lin.r, 1.0/2.4)-0.055;
    s.g = (lin.g <= 0.0031308) ? lin.g*12.92 : 1.055*pow(lin.g, 1.0/2.4)-0.055;
    s.b = (lin.b <= 0.0031308) ? lin.b*12.92 : 1.055*pow(lin.b, 1.0/2.4)-0.055;
    return s;
}

vec3 Gamma_rec709(vec3 lin) {
    return pow(lin, vec3(1.0/2.4));
}

vec3 gamma_p3(vec3 lin) {
    return pow(lin, vec3(1.0/2.6));
}

vec3 Aces(vec3 x) {
  const float a = 2.51;
  const float b = 0.03;
  const float c = 2.43;
  const float d = 0.59;
  const float e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

vec3 Gamma_corect(vec3 color){
    float n = Post_settings[0];
    if (n==0.){return Gamma_srgb_exact(color);}
    if (n==1.){return Gamma_rec709(color);}
    if (n==2.){return gamma_p3(color);}
    if (n==3.){return Aces(color);}
    if (n==4.){return color;} 
}

vec3 ChromaticAberration(sampler2D tex, vec2 uv, vec2 resolution, float amount) {
    vec2 dir = uv - 0.5; 
    float len = length(dir);
    vec2 offset = dir * amount * len / 8.;
    float r = texture(tex, uv).r;
    float g = texture(tex, uv - offset).g;
    float b = texture(tex, uv - 2. * offset).b;
    return vec3(r, g, b);
}
vec3 Highlight(sampler2D tex, vec2 uv, vec2 resolution, float threshold, float intensity) {
    vec2 texel = 1.0 / resolution;
    vec3 color = texture(tex, uv).rgb;
    vec3 bright = max(color - vec3(threshold), vec3(0.0));
    bright += texture(tex, uv + vec2(texel.x, 0)).rgb * 0.25;
    bright += texture(tex, uv + vec2(-texel.x, 0)).rgb * 0.25;
    bright += texture(tex, uv + vec2(0, texel.y)).rgb * 0.25;
    bright += texture(tex, uv + vec2(0, -texel.y)).rgb * 0.25;
    return bright * intensity;
}

float luminance(vec3 c) {
    return dot(c, vec3(0.2126, 0.7152, 0.0722)); // Rec.709
}

vec3 Saturation(vec3 color, float sat) {
    float l = luminance(color);
    return mix(vec3(l), color, sat);
}


void postProcess(out vec4 fragColor, vec2 fragCoord)
{
    vec2 uv = fragCoord / iResolution.xy;

    vec3 color = ChromaticAberration(uAccum, uv, iResolution.xy, Post_settings[5]);
    color = color * Post_settings[1] + Post_settings[2];
    color = min((color - vec3(0.5)) * Post_settings[4] + vec3(0.5), vec3(1.0));
    color = Saturation(color, Post_settings[3]);
    color = Gamma_corect(color);
    vec3 highlight = Highlight(uAccum, uv, iResolution.xy, 0.5, Post_settings[6]);
    fragColor = vec4(color + highlight, 1.0);
}
