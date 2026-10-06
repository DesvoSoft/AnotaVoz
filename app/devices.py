"""WASAPI device lookup via PyAudioWPatch.

Loopback is resolved by device index against the WASAPI host API's default
output device, not by string-matching device names — the prototype matched
`default_speaker.name in loopback_name`, which breaks whenever Windows
renames the loopback device differently from the speaker (varies by driver).
"""
import pyaudiowpatch as pyaudio


class DeviceError(Exception):
    pass


def _wasapi_info(p):
    try:
        return p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError as e:
        raise DeviceError("WASAPI not available on this system") from e


def default_mic(p):
    """Default input device under the WASAPI host API."""
    wasapi = _wasapi_info(p)
    index = wasapi["defaultInputDevice"]
    if index == -1:
        raise DeviceError("No default WASAPI input device (microphone) found")
    return p.get_device_info_by_index(index)


def default_loopback(p):
    """Loopback device for the default output (speaker/headphones).

    The default output device itself is not a loopback device — Windows
    exposes a *separate* loopback-flavored device per output. We resolve it
    by matching device index/name against the output's own info, falling
    back to the first loopback device available if that fails.
    """
    wasapi = _wasapi_info(p)
    out_index = wasapi["defaultOutputDevice"]
    if out_index == -1:
        raise DeviceError("No default WASAPI output device found")
    default_speaker = p.get_device_info_by_index(out_index)

    if default_speaker.get("isLoopbackDevice"):
        return default_speaker

    for loopback in p.get_loopback_device_info_generator():
        if default_speaker["name"] in loopback["name"]:
            return loopback

    for loopback in p.get_loopback_device_info_generator():
        return loopback

    raise DeviceError(
        "No loopback device found — enable 'Stereo Mix' or check WASAPI loopback support"
    )


def default_output(p):
    """The raw default output device (speaker/headphones), not its loopback
    twin — used to open a keep-alive silent stream (see capture.py)."""
    wasapi = _wasapi_info(p)
    out_index = wasapi["defaultOutputDevice"]
    if out_index == -1:
        raise DeviceError("No default WASAPI output device found")
    return p.get_device_info_by_index(out_index)


def list_input_devices(p):
    """All WASAPI input-capable devices (mics), for a future device picker."""
    wasapi = _wasapi_info(p)
    devices = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["hostApi"] == wasapi["index"] and info["maxInputChannels"] > 0:
            devices.append(info)
    return devices


def list_loopback_devices(p):
    return list(p.get_loopback_device_info_generator())
