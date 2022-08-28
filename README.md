# RadonPy
### Tools to communicate with the RadonEye RD200 radon detector

RadonPy provides a Python library for communicating with the [RadonEye RD200](http://radonftlab.com/radon-sensor-product/radon-detector/rd200/) radon detector over Bluetooth Low Energy, as well as a command line program to read sensor values and configure settings.

Note that devices newer than November 2021 are not currently supported. They switched from an Nordic nRF5x to an ESP32 and changed the protocol, and I don't have new hardware to test.
