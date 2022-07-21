# KiCad Tools
A collection of tools to help with importing and rendering KiCad PCBs in Blender.
## Installation
From Blender's "Preferences > Add-ons" menu select "Install" then select "kicad_tools.py"
## Tools
### Import KiCad PCB (File > Import > KiCad PCB)
Import a VRML (.wrl) file exported by KiCad. When exporting from KiCad the option to "Copy 3D model files to 3D model path" must be selected.
### Create KiCad Nodes (Object > Create KiCad Nodes)
Geometry nodes are generated for displacing and extruding PCB geometry. Other modifiers are also added to the PCB objects.
### Apply KiCad Modifiers (Object > Apply KiCad Modifiers)
Apply all modifiers added to KiCad objects. This dramatically improves performance.