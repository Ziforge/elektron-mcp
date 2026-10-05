"""
Preset transfer: CLI discovery, port handover and failure reporting.

No hardware and no elektroid-cli required -- the subprocess is faked.
"""

import subprocess

import pytest

from elektron_mcp.preset import elektroid
from elektron_mcp.tools.preset_tool import _port_handover


class FakeMidi:
    def __init__(self, connected=True):
        self.connected = connected
        self.output_port_name = "Elektron Digitone II" if connected else None
        self.events = []

    def disconnect(self):
        self.events.append("disconnect")
        self.connected = False

    def connect(self, port):
        self.events.append(f"connect:{port}")
        self.connected = True
        return True

    def auto_connect(self):
        self.events.append("auto_connect")
        self.connected = True
        return True


def test_port_is_released_and_restored():
    """Only one process can hold the port; Elektroid times out if this
    server keeps it, so the handover has to be automatic."""
    midi = FakeMidi()
    with _port_handover(midi):
        assert midi.connected is False, "port was not released"
    assert midi.connected is True
    assert midi.events == ["disconnect", "connect:Elektron Digitone II"]


def test_port_is_restored_even_when_the_transfer_raises():
    midi = FakeMidi()
    with pytest.raises(RuntimeError):
        with _port_handover(midi):
            raise RuntimeError("transfer blew up")
    assert midi.connected is True, "port left released after a failure"


def test_handover_does_nothing_when_no_port_was_held():
    midi = FakeMidi(connected=False)
    with _port_handover(midi):
        pass
    assert midi.events == []


def test_cli_path_prefers_the_environment(monkeypatch, tmp_path):
    fake = tmp_path / "elektroid-cli"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("ELEKTROID_CLI", str(fake))
    assert elektroid.cli_path() == str(fake)


def test_readiness_explains_a_missing_device_table(monkeypatch, tmp_path):
    """The subtle failure: handshake succeeds, Elektroid still reports a
    generic MIDI device because it has no table to look the ID up in."""
    monkeypatch.setattr(elektroid, "DEVICES_JSON", tmp_path / "absent.json")
    state = elektroid.readiness()
    assert state["devices_json_installed"] is False
    assert "devices.json" in state["note"]


def test_device_list_is_parsed(monkeypatch):
    monkeypatch.setattr(elektroid, "_run", lambda *a, **k: (
        "0: id: SYSTEM_ID; name: Mac.lan\n"
        "1: id: Elektron Digitone II; name: Elektron Digitone II\n"
    ))
    devices = elektroid.list_devices()
    assert [d["index"] for d in devices] == [0, 1]
    assert elektroid.find_device("digitone") == 1


def test_find_device_reports_what_it_saw(monkeypatch):
    monkeypatch.setattr(elektroid, "_run",
                        lambda *a, **k: "0: id: X; name: Something Else\n")
    with pytest.raises(elektroid.ElektroidError, match="Something Else"):
        elektroid.find_device("Digitone")


def test_generic_connector_is_flagged_as_a_warning(monkeypatch):
    monkeypatch.setattr(elektroid, "_run", lambda *a, **k: (
        "Type: MIDI\nDevice name: MIDI device\nConnector: default\n"
        "Filesystems: program\n"
    ))
    info = elektroid.device_info(1)
    assert info["connector"] == "default"
    assert "devices.json" in info["warning"]


def test_real_connector_has_no_warning(monkeypatch):
    monkeypatch.setattr(elektroid, "_run", lambda *a, **k: (
        "Device name: Elektron Digitone II\nConnector: elektron\n"
        "Filesystems: data (CLI only), preset-takt-ii, project\n"
    ))
    info = elektroid.device_info(1)
    assert info["connector"] == "elektron" and "warning" not in info


def test_missing_cli_is_an_explicit_error(monkeypatch):
    monkeypatch.setattr(elektroid, "cli_path", lambda: None)
    with pytest.raises(elektroid.ElektroidError, match="not found"):
        elektroid._run(["ld"], 5)


def test_timeout_names_the_command(monkeypatch, tmp_path):
    fake = tmp_path / "cli"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(elektroid, "cli_path", lambda: str(fake))

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(elektroid.ElektroidError, match="timed out"):
        elektroid._run(["ld"], 1)


def test_upload_refuses_a_missing_file(monkeypatch):
    monkeypatch.setattr(elektroid, "cli_path", lambda: "/bin/true")
    with pytest.raises(elektroid.ElektroidError, match="no such file"):
        elektroid.upload(1, "preset-takt-ii", "/nope/absent.bin", "/A/001")


def test_preset_tools_are_registered():
    import asyncio

    from elektron_mcp.mcp_server.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    for n in ("transfer_readiness", "list_device_presets",
              "list_device_projects", "download_preset", "upload_preset",
              "copy_device_preset", "backup_device_project"):
        assert n in names, f"{n} not registered"
