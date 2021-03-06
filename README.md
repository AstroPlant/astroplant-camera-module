# astroplant-camera-module structure
This repository exists of a couple of different folders. The most important ones are astroplant_camera_module; which is the actual Python code, tests; which contains tests that directly work with the module (so you should be able to run them fairly easily) and docs; which contains some background info, building scheme's, materials, etc. Start in the docs folder if you want more information on this project.

The supporting-scripts folder contains some simulations that are used in the full report (which can be found in the docs folder as well). The results folder contains some photos from various stages of testing, and is purely an indication of what kind of photos you can expect. I'm sure that you will be able to produce better ones when you implement this module in your operational kit. For some longer period testing results, be sure to take a look at the report or the shortened report in the docs folder.

# astroplant_camera_module code readme
Python3 code for the camera module in the astroplant kit. Exposed workings can be found in the module folder. In order to be able to load the module, it has to be added to the PYTHONPATH variable. This can be done permanently by adding the following line (correcting the folder location on your system) to the ~/.bashrc file:
```bash
# add astroplant camera module to python path
export PYTHONPATH="${PYTHONPATH}:/home/pi/git/astroplant-camera-module"
```
## Module with growth lighting only (V5 of the kit)
Short tl;dr:
When you simply want to take photos of your plant, you can use the camera in combination with the growth lighting. Note that for optimal results, growth lighting should be consistent when taking photo's, and set to a bright setting (all colors 75% for example). It is the responsibility of the user that the lighting is set up correctly when taking the photo, as this module cannot influence those settings. The only thing that needs to be loaded are the settings for the camera. This can be done as follows:
```python3
from astroplant_camera_module.cameras.pi_cam_noir_v21 import PI_CAM_NOIR_V21, SETTINGS_V5

settings = SETTINGS_V5()
```
The actual camera object can then be loaded by calling:
```python3
cam = PI_CAM_NOIR_V21(settings = settings)
```
To see what commands can be called, scroll down below.
## Module with seperate LED lights (NDVI measurements etc)
Short tl;dr:
In order to create a camera object that actually does something, the module needs to know how to control the lights in the Astroplant kit. Note that it is the responsibility of the user that the lighting is set up correctly when taking the photo, meaning that the growth lighting is off when commands are called. There are multiple ways to Rome here, so you as the user are asked to supply a function with the following characteristics:
```python3
def light_control(channel: LC, state):
    """
    Function that controls the lighting in the kit.

    :param channel: light channel that is to be controlled (ex: LC.WHITE)
    :param state: 0 for lights off, 1 for lights on

    :return: empty
    """
```
Note here that the light channels actually use a helper object to ensure consistency. All available channels can be found in the astroplant_camera_module/typedef.py file and are (at the moment of writing) as follows:
```python3
class LC(object):
    """
    (L)ight (C)hannel: Class holding the possible channels that can be used to light the kit
    """

    WHITE = "white"
    RED = "red"
    NIR = "nir"

    GROWTH = "growth"
```
In the case where the pigpio module is used, the function can be constructed in the script using the camera like this:
```python3
import pigpio
import time
from astroplant_camera_module.typedef import CC, LC
from astroplant_camera_module.misc.debug_print import d_print

def light_control_curry(pi):
    def light_control(channel: LC, state):
        d_print("Setting {} camera lighting state to {}".format(channel, state), 1)

        if channel == LC.WHITE:
            pi.write(17, state)
        elif channel == LC.RED:
            pi.write(3, state)
        elif channel == LC.NIR:
            pi.write(4, state)
        else:
            d_print("no such light available", 3)

        time.sleep(0.1)

    return light_control

pi = pigpio.pi()
light_control = light_control_curry(pi)
```
Secondly, you need to expose to the camera which channels are actually available to it. This is used to calibrate the available channels and to check if certain actions are allowed. Make sure that all channels given to the camera actually can be called in the light function you supplied to ensure correct operation. These channels can be saved in a list.
```python3
light_channels = [LC.WHITE, LC.RED, LC.NIR]
```
Lastly, different versions of the kit can be in production, so the correct set of settings needs to be loaded. Settings are supplied with the camera in the same file, and can be loaded like this:
```python3
from astroplant_camera_module.cameras.pi_cam_noir_v21 import PI_CAM_NOIR_V21, SETTINGS_V5

settings = SETTINGS_V5()
```
Finally, you can make a camera object by creating an instance of the camera you want, supplying the above:
```python3
cam = PI_CAM_NOIR_V21(light_control = light_control, light_channels = light_channels, settings = settings)
```
Due to the relatively memory intensive nature of the module, it is recommended that the camera object is destroyed every time after it is finished processing the photos / values. Generally, the frequency of taking the photos will be so low (2-4 times a day) that this will not lead to a significant increase in latency. This can be done by calling the following after all commands have been processed:
```python3
del cam
```
## Available commands
All available commands are listed in the astroplant_camera_module/typedef.py file, under the CC object:
```python3
class CC(object):
    """
    (C)amera (C)ommand: Class holding the possible types of commands that can be performed by the camera.
    """

    # regular photo (visible spectrum: ~400-700 nm, color balanced)
    WHITE_PHOTO = "WHITE_PHOTO"
    # photo using growth lighting: as balanced as possible, colors will probably be off
    GROWTH_PHOTO = "GROWTH_PHOTO"
    # NDVI photo (NIR vs red spectrum: ~850 nm vs ~630 nm)
    NDVI_PHOTO = "NDVI_PHOTO"
    # NIR photo (NIR spectrum: ~850 nm)
    NIR_PHOTO = "NIR_PHOTO"
    # leaf mask (should produce a black/white mask that masks out the leaves)
    #LEAF_MASK = "LEAF_MASK"

    # averaged ndvi value of the plant (all material with ndvi > 0.2)
    NDVI = "NDVI"

    # calibrate the camera and the lights
    CALIBRATE = "CALIBRATE"
    # update camera settings if camera needs this (for example, redetermine gains etc)
    UPDATE = "UPDATE"
```
Commands can be called as follows:
```python3
cam.do(CC.CALIBRATE)
cam.do(CC.UPDATE)
print(cam.do(CC.WHITE_PHOTO))
print(cam.do(CC.GROWTH_PHOTO))
print(cam.do(CC.NDVI_PHOTO))
```
To check the current camera state, run:
```python3
cam.state()
```
## Return values
Values and photos are returned to the user in a specific standard format, contained in a Python dict. This way the user can always see if an error was encountered, and whether the return contains images or values. The encountered_error, contains_photo, contains_value and timestamp field are always set. Returns from functions will look, depending on the command send, as follows:
```python3
{
    'photo_kind':
        [
            'raw NDVI',
            'processed NDVI'
        ],
    'encountered_error': False,
    'value_kind': ['NDVI'],
    'value_error': [0.0],
    'timestamp': '20190606-140728',
    'contains_value': True,
    'contains_photo': True,
    'value': [0.3598392680470938],
    'photo_path':
        [
            '.../astroplant-camera-module/tests/cam/img/ndvi1_20190606-140728.tif',
            '.../astroplant-camera-module/tests/cam/img/ndvi2_20190606-140728.jpg'
        ]
}
```
## Tinkering with the code
For production purposes the amount of information printed to the terminal is limited. If you are working on the code, or want to try something new you can re-enable all debug printing in the code. In the astroplant_camera_module/misc/debug_print.py file, you will find a SEVERITY parameter, which is set to the error level in production code. If you lower the level to debug (1), all extra information will again be printed to the terminal.
