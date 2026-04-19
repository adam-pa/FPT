# FPT - Fractal Path Tracer 
FPT is a free sdf and open-source path tracer! <br>
If you have any suggestions would love to hear them! <br>
Also if you make any cool renders pls send them, I love seeing my program in use ;) <br>
My insta: https://www.instagram.com/adamp.art/ 
<br>
<br>

## Creating SDFs in FPT
In FPT, you define objects using Signed Distance Functions (SDFs) written in GLSL. <br>
An SDF calculates the shortest distance between a given point in space and the surface of an object.

### The Basics 
To create a shape, go to the "sdf" tab and assign a value to the sdf variable. <br>
This is calculated based on ```p```, which represents the current position vector. <br>
An example sphere sdf:
```
sdf = length(p) - 1.0;
```
### Helper Functions
If for example you want do define a function you have to do it in the "Helper functions" tab. <br> 
An example sphere sdf function:
```
float sdSphere(vec3 p, float radius) {
  return length(p) - radius;
}
```
You can also define surface properties within the sdf tab using the ```material``` struct:
```
material.rgb          = vec3(1.0); // Surface color
material.roughness    = 1.0;       // Surface micro-detail
material.specular     = 0.0;       // Reflectivity
material.translucency = 0.0;       // Translucency
material.ior          = 1.5;       // Index of Refraction
material.emission     = 0.0;       // Emission intensity
```


## Sample Scenes
You can find .txt files in the `Sample scenes/` directory, that has examples for you to try out, by pasting in to FPT.
  
--------
![Render005](https://github.com/user-attachments/assets/64d05615-bc69-4160-a27d-92a1a1b1ac41)
<img width="1920" height="1080" alt="Render_14" src="https://github.com/user-attachments/assets/d1caa0c9-73d1-4c21-aba8-faee8d2d6639" />

<img width="49%" alt="Cornell box" src="https://github.com/user-attachments/assets/7e021897-da35-4637-9a05-cdaf2bfed38c" /> <img width="49%" alt="Glass_Ball" src="https://github.com/user-attachments/assets/b2adcce5-b7a1-4624-8834-804ca24864b2" />

<img width="49%" alt="Screenshot_2" src="https://github.com/user-attachments/assets/54d24eee-c9c0-401c-b880-d95d23015d09" /> <img width="49%" alt="Screenshot_2" src="https://github.com/user-attachments/assets/363daa34-3713-46b0-83bb-95c0d0c50fdf" />

<img width="49%" alt="M4" src="https://github.com/user-attachments/assets/0064a3e8-6c5e-40c9-97f3-a53d34c466e0" /> <img width="49%" alt="Render0ad03" src="https://github.com/user-attachments/assets/2bcfe47a-2f49-4696-a681-25942a8b5f30" />

<img width="1920" height="1080" alt="Glass!!" src="https://github.com/user-attachments/assets/92c1ba29-06af-4317-856e-1bff9b43f41e" />

