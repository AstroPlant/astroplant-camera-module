"""
Implementation for the Pi Camera V2.1
Should be similar for other camera's connected to the CSI interface on the Raspberry Pi
"""

import time
import picamera.array
import picamera
import os
import cv2
import numpy as np
import subprocess
import multiprocessing as mp

from fractions import Fraction
from PIL import Image

from astroplant_camera_module.core.camera import CAMERA
from astroplant_camera_module.core.ndvi import NDVI
from astroplant_camera_module.misc.debug_print import d_print
from astroplant_camera_module.typedef import LC
from astroplant_camera_module.misc.helper import light_control_dummy


class SETTINGS_V5(object):
    def __init__(self, *args, **kwargs):
        self.resolution = (1632,1216)

        self.framerate = dict()
        self.framerate[LC.WHITE] = Fraction(10, 4)
        self.framerate[LC.GROWTH] = 30

        self.shutter_speed = dict()
        self.shutter_speed[LC.WHITE] = 400000
        self.shutter_speed[LC.GROWTH] = 4000

        self.ground_plane = dict()
        self.ground_plane["x_min"] = 445
        self.ground_plane["x_max"] = 1265
        self.ground_plane["y_min"] = 40
        self.ground_plane["y_max"] = 860

        self.crop = dict()
        self.crop["x_min"] = 0
        self.crop["x_max"] = self.resolution[0]
        self.crop["y_min"] = 0
        self.crop["y_max"] = self.resolution[1]

        self.wb = dict()
        self.wb[LC.GROWTH] = dict()
        self.wb[LC.GROWTH]["r"] = 0.4
        self.wb[LC.GROWTH]["b"] = 0.575

        self.exposure_mode = "off"
        self.exposure_compensation = 0

        self.allowed_channels = [LC.WHITE, LC.GROWTH]


class PI_CAM_V21(CAMERA):
    def __init__(self, *args, light_control = light_control_dummy, light_channels = [LC.GROWTH], settings, working_directory = os.getcwd(), **kwargs):
        """
        Initialize an object that contains the visible routines.
        Link the pi and gpio pins necessary and provide a function that controls the growth lighting.

        :param light_control: function that allows control over the lighting. Parameters are the channel to control and either a 0 or 1 for off and on respectively
        :param light_channels: list containing allowable light channels
        :param settings: reference to one of the settings object contained in this file. These settings are used to control shutter speeds, resolutions, crops etc.
        """

        # set up the camera super class
        super().__init__(light_control = light_control, working_directory = working_directory)

        # give the camera a unique ID per brand/kind/etc, software uses this ID to determine whether the
        # camera is calibrated or not
        self.CAM_ID = 2
        # enable update function to update gains
        self.HAS_UPDATE = True

        # bind the settings to the camera object
        self.settings = settings

        # set up the light channel array
        self.light_channels = []
        for channel in light_channels:
            if channel in self.settings.allowed_channels:
                self.light_channels.append(channel)

        # load config file and check if it matches the cam id, if so, assume calibrated
        try:
            self.load_config_from_file()
            if self.config["cam_id"] == self.CAM_ID:
                self.CALIBRATED = True
                d_print("Succesfully loaded suitable camera configuration.", 1)
            else:
                self.CALIBRATED = False
                d_print("Found camera configuration file, but contents are not suitable for current camera.", 3)
        except (EnvironmentError, ValueError):
            d_print("No suitable camera configuration file found!", 3)
            self.CALIBRATED = False

        # set multiprocessing to spawn (so NOT fork)
        try:
            mp.set_start_method('spawn')
        except RuntimeError:
            pass


    def update(self):
        """
        Function that updates the gains needed to expose the image correctly. Saves it to the configuration file.
        """

        # check if gain information is available, if not, update config
        if "d2d" not in self.config:
            self.setup_d2d()

        for channel in self.light_channels:
            # turn on the light
            self.light_control(channel, 1)

            d_print("Letting gains settle for the {} channel...".format(channel), 1)

            with picamera.PiCamera() as sensor:
                # set up the sensor with all its settings
                sensor.resolution = self.settings.resolution
                sensor.framerate = self.settings.framerate[channel]
                sensor.shutter_speed = self.settings.shutter_speed[channel]

                sensor.awb_mode = "off"
                sensor.awb_gains = (self.config["wb"][channel]["r"], self.config["wb"][channel]["b"])

                time.sleep(30)

                sensor.exposure_mode = self.settings.exposure_mode

                # set the analog and digital gain
                ag = float(sensor.analog_gain)
                dg = float(sensor.digital_gain)

                self.config["d2d"][channel]["digital-gain"] = dg
                self.config["d2d"][channel]["analog-gain"] = ag

                d_print("Measured ag: {} and dg: {} for channel {}".format(ag, dg, channel), 1)
                d_print("Saved ag: {} and dg: {} for channel {}".format(self.config["d2d"][channel]["analog-gain"], self.config["d2d"][channel]["digital-gain"], channel), 1)

            # turn the light off
            self.light_control(channel, 0)

        # update timestamp
        self.config["d2d"]["timestamp"] = time.time()

        # save the new configuration to file
        self.save_config_to_file()


    def capture(self, channel: LC):
        """
        Function that captures an image. Uses raspistill in a separate terminal process to take the picture. This is faster (about 4-5 seconds to take an image on average) due to the possibility to manually set the gains of the camera, something that is not possible in picamera 1.13 (but will probably be in version 1.14 or 1.15).

        :param channel: channel of light in which the photo is taken, used for white balance and gain values
        :return: 8 bit rgb array containing the image
        """

        # check if gain information is available, if not, update first
        if "d2d" not in self.config:
            self.setup_d2d()
            self.update()

        # turn on the light
        self.light_control(channel, 1)

        # assemble the terminal command
        path_to_bright = os.getcwd() + "/cam/tmp/bright.bmp"
        path_to_dark = os.getcwd() + "/cam/tmp/dark.bmp"
        gain = self.config["d2d"][channel]["analog-gain"] * self.config["d2d"][channel]["digital-gain"]

        photo_cmd = "raspistill -e bmp -w {} -h {} -ss {} -t 1000 -awb off -awbg {},{} -ag {} -dg {}".format(self.settings.resolution[0], self.settings.resolution[1], self.settings.shutter_speed[channel], self.config["wb"][channel]["r"], self.config["wb"][channel]["b"], self.config["d2d"][channel]["analog-gain"], self.config["d2d"][channel]["digital-gain"])

        # run command and take bright and dark picture
        # start the bright image capture by spawning a clean process and executing the command, then waiting for the q
        p = mp.Process(target=photo_worker, args=(photo_cmd + " -o {}".format(path_to_bright),))
        try:
            p.start()
            p.join()
        except OSError:
            d_print("Could not start child process, out of memory", 3)
            return (None, 0)
        # turn off the light
        self.light_control(channel, 0)
        # start the dark image capture by spawning a clean process and executing the command, then waiting for the q
        p = mp.Process(target=photo_worker, args=(photo_cmd + " -o {}".format(path_to_dark),))
        try:
            p.start()
            p.join()
        except OSError:
            d_print("Could not start child process, out of memory", 3)
            return (None, 0)

        # load the images from file, perform dark frame subtraction and return the array
        bright = Image.open(path_to_bright)
        rgb = np.array(bright)
        if channel != LC.GROWTH:
            dark = Image.open(path_to_dark)
            rgb = cv2.subtract(rgb, np.array(dark))

        # if the time since last update is larger than a day, update the gains after the photo
        if time.time() - self.config["d2d"]["timestamp"] > 3600*24:
            self.update()

        return (rgb, gain)


    def calibrate_white_balance(self, channel: LC):
        """
        Function that calibrates the white balance for certain lighting specified in the channel parameter. This is camera specific, so it needs to be specified for each camera.

        :param channel: light channel that needs to be calibrated
        """

        d_print("Warming up camera sensor...", 1)

        # turn on channel light
        self.light_control(channel, 1)

        if channel == LC.WHITE:
            with picamera.PiCamera() as sensor:
                # set up the sensor with all its settings
                sensor.resolution = (128, 80)
                sensor.rotation = self.config["rotation"]
                sensor.framerate = self.settings.framerate[channel]
                sensor.shutter_speed = self.settings.shutter_speed[channel]

                # set up the blue and red gains
                sensor.awb_mode = "off"
                rg, bg = (1.1, 1.1)
                sensor.awb_gains = (rg, bg)

                # now sleep and lock exposure
                time.sleep(20)
                sensor.exposure_mode = self.settings.exposure_mode

                # record camera data to array and scale up a numpy array
                #rgb = np.zeros((1216,1216,3), dtype=np.uint16)
                with picamera.array.PiRGBArray(sensor) as output:
                    # capture images and analyze until convergence
                    for i in range(30):
                        output.truncate(0)
                        sensor.capture(output, 'rgb')
                        rgb = np.copy(output.array)

                        #crop = rgb[508:708,666:966,:]
                        crop = rgb[30:50,32:96,:]

                        r, g, b = (np.mean(crop[..., i]) for i in range(3))
                        d_print("\trg: {:4.3f} bg: {:4.3f} --- ({:4.1f}, {:4.1f}, {:4.1f})".format(rg, bg, r, g, b), 1)

                        if abs(r - g) > 1:
                            if r > g:
                                rg -= 0.025
                            else:
                                rg += 0.025
                        if abs(b - g) > 1:
                            if b > g:
                                bg -= 0.025
                            else:
                                bg += 0.025

                        sensor.awb_gains = (rg, bg)
        else:
            rg = self.settings.wb[LC.GROWTH]["r"]
            bg = self.settings.wb[LC.GROWTH]["b"]

        # turn off channel light
        self.light_control(channel, 0)

        self.config["wb"][channel] = dict()
        self.config["wb"][channel]["r"] = rg
        self.config["wb"][channel]["b"] = bg

        d_print("Done.", 1)


    def setup_d2d(self):
        """
        Function that sets up the fields required for the update function to work. These are saved in explicit dicts so that the chances of errors are minimal.
        """

        self.config["d2d"] = dict()

        self.config["d2d"][LC.WHITE] = dict()
        self.config["d2d"][LC.GROWTH] = dict()

        self.config["d2d"][LC.WHITE]["analog-gain"] = 1.0
        self.config["d2d"][LC.WHITE]["digital-gain"] = 1.0
        self.config["d2d"][LC.GROWTH]["analog-gain"] = 1.0
        self.config["d2d"][LC.GROWTH]["digital-gain"] = 1.0

        self.config["d2d"]["timestamp"] = time.time()

        self.save_config_to_file()


def photo_worker(cmd):
    """
    Function that executes a photo command. Because of the implementation of subprocess (which forks the entire process) a new thread is first made with a way smaller footprint. This ensures that memory usage stays as low as possible and the program doesn't crash when memory gets scarce.

    :param q: Queue in which a signal is posted when the photo is done
    :param cmd: Photo command to be executed
    """

    subprocess.run(cmd, shell=True, timeout=20)
