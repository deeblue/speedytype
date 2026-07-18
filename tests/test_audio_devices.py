from __future__ import annotations

from speedytype import audio


def test_selectable_devices_excludes_unopenable_and_generic_aliases(monkeypatch):
    devices = [
        {
            "name": "Microsoft Sound Mapper - Input",
            "max_input_channels": 2,
            "hostapi": 0,
            "default_samplerate": 44100.0,
        },
        {
            "name": "Primary Sound Capture Driver",
            "max_input_channels": 2,
            "hostapi": 1,
            "default_samplerate": 44100.0,
        },
        {
            "name": "Microphone Array",
            "max_input_channels": 2,
            "hostapi": 1,
            "default_samplerate": 44100.0,
        },
        {
            "name": "Stereo Mix",
            "max_input_channels": 2,
            "hostapi": 2,
            "default_samplerate": 48000.0,
        },
        {
            "name": "Speakers",
            "max_input_channels": 0,
            "hostapi": 2,
            "default_samplerate": 48000.0,
        },
    ]
    checked = []

    monkeypatch.setattr(audio.sd, "query_devices", lambda: devices)

    def fake_check_input_settings(*, device, samplerate, channels):
        checked.append((device, samplerate, channels))
        assert samplerate == audio.SAMPLE_RATE
        assert channels == audio.CHANNELS
        if device == 3:
            raise RuntimeError("Invalid sample rate")

    monkeypatch.setattr(audio.sd, "check_input_settings", fake_check_input_settings)

    assert [item["name"] for item in audio.list_selectable_input_devices()] == [
        "Microphone Array"
    ]
    assert checked == [
        (2, audio.SAMPLE_RATE, audio.CHANNELS),
        (3, audio.SAMPLE_RATE, audio.CHANNELS),
    ]


def test_selectable_devices_deduplicates_names_after_first_usable_device(monkeypatch):
    devices = [
        {
            "name": "USB Mic",
            "max_input_channels": 1,
            "hostapi": 0,
            "default_samplerate": 44100.0,
        },
        {
            "name": "USB Mic",
            "max_input_channels": 1,
            "hostapi": 1,
            "default_samplerate": 48000.0,
        },
    ]

    monkeypatch.setattr(audio.sd, "query_devices", lambda: devices)
    monkeypatch.setattr(audio.sd, "check_input_settings", lambda **kwargs: None)

    selectable = audio.list_selectable_input_devices()

    assert len(selectable) == 1
    assert selectable[0]["index"] == 0
