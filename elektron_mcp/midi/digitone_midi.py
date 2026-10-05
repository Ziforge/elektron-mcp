"""
Digitone MIDI Interface

This module handles MIDI communication with Elektron Digitone devices.
It provides functionality for connecting to Digitone over MIDI (USB),
selecting channels, and sending control change (CC) messages, including
the complete 14-bit NRPN sequence (CC 99, CC 98, CC 6, CC 38).
"""

import mido
import threading
import time
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

# MIDI Standard Control Change (CC) numbers for NRPN
NRPN_MSB_CC = 99  # CC for Non-Registered Parameter Number MSB
NRPN_LSB_CC = 98  # CC for Non-Registered Parameter Number LSB
DATA_ENTRY_MSB_CC = 6
DATA_ENTRY_LSB_CC = 38


class DigitoneMIDI:
    """Interface for MIDI communication with Elektron Digitone."""

    def __init__(self, port_name: Optional[str] = None):
        """
        Initialize the Digitone MIDI interface.

        Args:
            port_name: Name of the MIDI port to use. If None, will attempt to auto-detect.
        """
        self.input_port = None
        self.output_port = None
        self.connected = False
        self.output_port_name: Optional[str] = None
        self._captured: list = []
        self._capturing = False
        self._capture_thread: Optional[threading.Thread] = None

        if port_name:
            self.connect(port_name)
        else:
            self.auto_connect()

    def list_ports(self) -> List[str]:
        """List available MIDI ports."""
        inputs = mido.get_input_names()
        outputs = mido.get_output_names()
        return list(set(inputs + outputs))

    def auto_connect(self) -> bool:
        """
        Automatically connect to the first available Digitone device.

        Returns:
            bool: True if connection successful, False otherwise.
        """
        ports = self.list_ports()
        digitone_ports = [port for port in ports if "digitone" in port.lower()]

        if digitone_ports:
            return self.connect(digitone_ports[0])
        else:
            logger.warning("No Digitone device found. Available ports: %s", ports)
            return False

    def connect(self, port_name: str) -> bool:
        """
        Connect to the specified MIDI port.

        Args:
            port_name: Name of the MIDI port to connect to

        Returns:
            bool: True if connection successful, False otherwise.
        """
        try:
            # Close existing connections if any
            self.disconnect()

            # Open new connections
            self.output_port = mido.open_output(port_name)
            try:
                self.input_port = mido.open_input(port_name)
            except (IOError, ValueError) as e:
                logger.warning(f"Could not open input port {port_name}: {e}")
                # Continue with just output port

            self.connected = True
            self.output_port_name = port_name
            logger.info(f"Connected to MIDI port: {port_name}")
            return True
        except (IOError, ValueError) as e:
            logger.error(f"Failed to connect to MIDI port {port_name}: {e}")
            self.disconnect()
            return False

    def disconnect(self) -> None:
        """Close all MIDI connections."""
        if self.input_port:
            self.input_port.close()
            self.input_port = None

        if self.output_port:
            self.output_port.close()
            self.output_port = None

        self.connected = False

    def send_cc(self, channel: int, cc: int, value: int) -> bool:
        """
        Send a Control Change (CC) message.

        Args:
            channel: MIDI channel (1-16)
            cc: Control Change number (0-127)
            value: Control Change value (0-127)

        Returns:
            bool: True if message sent successfully, False otherwise.
        """
        if not self.connected or not self.output_port:
            logger.error("Not connected to any MIDI port")
            return False

        # Convert 1-indexed channel to 0-indexed
        if 1 <= channel <= 16:
            channel = channel - 1
        else:
            logger.error(f"Invalid channel: {channel}. Must be between 1-16.")
            return False

        try:
            # Create and send the CC message
            msg = mido.Message(
                "control_change", channel=channel, control=cc, value=value
            )
            self.output_port.send(msg)
            logger.debug(f"Sent CC: channel={channel+1}, cc={cc}, value={value}")
            return True
        except Exception as e:
            logger.error(f"Error sending CC message: {e}")
            return False

    def open_input(self, port_name: Optional[str] = None) -> bool:
        """
        Open a MIDI input port so the device can be listened to.

        connect() already opens one when the port allows it; this reopens it
        after a close, or points at a different port.

        Args:
            port_name: Input port name, or None to reuse the connected port.

        Returns:
            bool: True if an input port is open.
        """
        name = port_name or self.output_port_name
        if name is None:
            logger.error("No input port name available")
            return False
        try:
            if self.input_port is not None:
                self.input_port.close()
            self.input_port = mido.open_input(name)
            logger.info(f"Opened MIDI input: {name}")
            return True
        except Exception as e:
            logger.error(f"Could not open MIDI input {name!r}: {e}")
            return False

    def start_capture(self) -> bool:
        """
        Begin collecting incoming MIDI into a buffer.

        The Digitone only emits CC/NRPN when 'Send CC/NRPN' is enabled in its
        MIDI config, so an empty capture can mean the setting is off rather
        than that the device sent nothing.

        Returns:
            bool: True if capture started.
        """
        if self.input_port is None and not self.open_input():
            return False
        self._captured.clear()
        self._capturing = True
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True
        )
        self._capture_thread.start()
        return True

    def _capture_loop(self) -> None:
        while self._capturing and self.input_port is not None:
            for msg in self.input_port.iter_pending():
                self._captured.append((time.time(), msg))
            time.sleep(0.002)

    def stop_capture(self) -> list:
        """
        Stop collecting and return everything captured.

        Returns:
            list: (timestamp, mido.Message) pairs in arrival order.
        """
        self._capturing = False
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=1.0)
            self._capture_thread = None
        return list(self._captured)

    @property
    def captured(self) -> list:
        """Messages captured so far, without stopping the capture."""
        return list(self._captured)

    def send_note_on(self, channel: int, note: int, velocity: int = 100) -> bool:
        """
        Send a Note On message.

        Args:
            channel: MIDI channel (1-16), i.e. the Digitone track.
            note: Note number (0-127).
            velocity: Note velocity (1-127).

        Returns:
            bool: True if the message was sent successfully.
        """
        return self._send_note("note_on", channel, note, velocity)

    def send_note_off(self, channel: int, note: int) -> bool:
        """
        Send a Note Off message.

        Args:
            channel: MIDI channel (1-16), i.e. the Digitone track.
            note: Note number (0-127).

        Returns:
            bool: True if the message was sent successfully.
        """
        return self._send_note("note_off", channel, note, 0)

    def _send_note(self, kind: str, channel: int, note: int, velocity: int) -> bool:
        if not self.connected or not self.output_port:
            logger.error("Not connected to any MIDI port")
            return False

        if not 1 <= channel <= 16:
            logger.error(f"Invalid channel: {channel}. Must be between 1-16.")
            return False

        if not 0 <= note <= 127:
            logger.error(f"Invalid note: {note}. Must be between 0-127.")
            return False

        try:
            self.output_port.send(
                mido.Message(
                    kind,
                    channel=channel - 1,
                    note=note,
                    velocity=max(0, min(127, velocity)),
                )
            )
            logger.debug(f"Sent {kind}: channel={channel}, note={note}, vel={velocity}")
            return True
        except Exception as e:
            logger.error(f"Error sending {kind} message: {e}")
            return False

    def send_program_change(self, channel: int, program: int) -> bool:
        """
        Send a Program Change message, used to select a Digitone sound/pattern slot.

        Args:
            channel: MIDI channel (1-16).
            program: Program number (0-127).

        Returns:
            bool: True if the message was sent successfully.
        """
        if not self.connected or not self.output_port:
            logger.error("Not connected to any MIDI port")
            return False

        if not 1 <= channel <= 16:
            logger.error(f"Invalid channel: {channel}. Must be between 1-16.")
            return False

        try:
            self.output_port.send(
                mido.Message("program_change", channel=channel - 1, program=program)
            )
            return True
        except Exception as e:
            logger.error(f"Error sending program change: {e}")
            return False

    def all_notes_off(self, channel: Optional[int] = None) -> bool:
        """
        Send All Notes Off (CC 123) plus an explicit note-off sweep.

        The CC alone is ignored by some firmware revisions, so the sweep is sent
        as well to guarantee silence.

        Args:
            channel: MIDI channel (1-16), or None for every channel.

        Returns:
            bool: True if every message was sent successfully.
        """
        channels = [channel] if channel is not None else list(range(1, 17))
        ok = True
        for ch in channels:
            ok = self.send_cc(ch, 123, 0) and ok
            for note in range(128):
                ok = self.send_note_off(ch, note) and ok
        return ok

    def send_nrpn(self, channel: int, nrpn_msb: int, nrpn_lsb: int, value: int) -> bool:
        """
        Send a Non-Registered Parameter Number (NRPN) message sequence (14-bit).

        Sends:
          1. CC 99 (NRPN MSB)
          2. CC 98 (NRPN LSB)
          3. CC 6  (Data Entry MSB)
          4. CC 38 (Data Entry LSB)

        Elektron expects the complete 14-bit sequence even if you only need 7-bit resolution.

        Args:
            channel: MIDI channel (1-16)
            nrpn_msb: NRPN Parameter MSB (0-127)
            nrpn_lsb: NRPN Parameter LSB (0-127)
            value: 14-bit value (0-16383) or 7-bit (0-127)

        Returns:
            bool: True if all messages sent successfully, False otherwise.
        """
        if not self.connected or not self.output_port:
            logger.error("Not connected to any MIDI port")
            return False

        # Convert 1-indexed channel to 0-indexed
        if 1 <= channel <= 16:
            channel_idx = channel - 1
        else:
            logger.error(f"Invalid channel: {channel}. Must be between 1-16.")
            return False

        try:
            # MSB/LSB for the parameter ID
            self.output_port.send(
                mido.Message(
                    "control_change",
                    channel=channel_idx,
                    control=NRPN_MSB_CC,
                    value=nrpn_msb,
                )
            )
            self.output_port.send(
                mido.Message(
                    "control_change",
                    channel=channel_idx,
                    control=NRPN_LSB_CC,
                    value=nrpn_lsb,
                )
            )

            # If 'value' is only 0-127, just use DataEntry MSB as 'value' and LSB as 0
            # If 'value' can be 0-16383, split it:
            value_msb = (value >> 7) & 0x7F
            value_lsb = value & 0x7F

            # Data Entry MSB
            self.output_port.send(
                mido.Message(
                    "control_change",
                    channel=channel_idx,
                    control=DATA_ENTRY_MSB_CC,
                    value=value_msb,
                )
            )
            # Data Entry LSB
            self.output_port.send(
                mido.Message(
                    "control_change",
                    channel=channel_idx,
                    control=DATA_ENTRY_LSB_CC,
                    value=value_lsb,
                )
            )

            logger.debug(
                f"Sent NRPN: channel={channel}, NRPN={nrpn_msb}/{nrpn_lsb}, "
                f"valueMSB={value_msb}, valueLSB={value_lsb}"
            )
            return True
        except Exception as e:
            logger.error(f"Error sending NRPN message: {e}")
            return False
