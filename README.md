# astroplant_camera_module documentation
Python3 code for the camera module in the astroplant kit. Exposed workings can be found in the text folder. Short tl;dr:
In order to create a camera object that actually does something, the module needs to know how to control the lights in the Astroplant kit. There are multiple ways to Rome here, so you as the user are asked to supply a function with the following characteristics:
```python3
def light_control(channel: LC, state):
    """
    Function that controls the lighting in the kit.

    :param channel: light channel that is to be controlled (ex: LC.WHITE)
    :param state: 0 for lights off, 1 for lights on

    :return: empty
    """
```
Note here that the light channels actually use a helper object to make sure that typos don't happen. All available channels can be found in the astroplant_camera_module/typedef.py file and are (at the moment of writing) as follows:
```python3
class LC(object):
    """
    (L)ight (C)hannel: Class holding the possible channels that can be used to light the kit
    """

    WHITE = "white"
    RED = "red"
    NIR = "nir"
```
In the case where the pigpio module is used, the function can be constructed in the script using the camera like this:
```python3
import pigpio
import time
from astroplant_camera_module.typedef import CC, LC

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
All available commands are listed in the astroplant_camera_module/typedef.py file, under the CC object:
```python3
class CC(object):
    """
    (C)amera (C)ommand: Class holding the possible types of commands that can be performed by the camera.
    """

    # regular photo (visible spectrum: ~400-700 nm, color balanced)
    REGULAR_PHOTO = "REGULAR_PHOTO"
    # NDVI photo (NIR vs red spectrum: ~850 nm vs ~630 nm)
    NDVI_PHOTO = "NDVI_PHOTO"
    # NIR photo (NIR spectrum: ~850 nm)
    NIR_PHOTO = "NIR_PHOTO"
    # leaf mask (should produce a black/white mask that masks out the leaves)
    LEAF_MASK = "LEAF_MASK"

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
print(cam.do(CC.REGULAR_PHOTO))
print(cam.do(CC.NDVI_PHOTO))
```
To check the current camera state, run:
```python3
cam.state()
```
