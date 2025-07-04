from contextlib import contextmanager
from collections import namedtuple
from enum import Enum
from tcp_scpi import SCPIClient
from typing import Literal


class OutputMode(Enum):
    ConstantVoltage = "CV"
    ConstantCurrent = "CV"
    Unregulated = "UR"


Measurement = namedtuple("Measurement", ["voltage", "current", "power"])
Output = namedtuple("Output", ["voltage", "current"])


class OverProtectiveParent:
    def __init__(
            self,
            channel: int,
            protecting: Literal["CURRent", "VOLTage"],
            scpi: SCPIClient
    ):
        self._channel = channel
        self._scpi = scpi
        self._protecting = protecting
        self._source_id = f":SOURCe[{self._channel}]"

    @contextmanager
    def __call__(self, level: float):
        try:
            self.clear()
            self.level = level
            self.state = True
            yield
        finally:
            self.state = False

    @property
    def state(self) -> bool:
        return self._scpi.query(
            f"{self._source_id}:{self._protecting}:PROT:STAT?") == "1"

    @state.setter
    def state(self, value: bool):
        self._scpi.send(
            f"{self._source_id}:{self._protecting}:PROT:STAT "
            f"{'ON' if value else 'OFF'}")

    @property
    def level(self) -> float:
        return float(self._scpi.query(
            f"{self._source_id}:{self._protecting}:PROT?"))

    @level.setter
    def level(self, value: float):
        self._scpi.send(
            f"{self._source_id}:{self._protecting}:PROT {value:.3f}")

    @property
    def tripped(self) -> bool:
        """whether the current protection tripped"""
        return self._scpi.query(
            f"{self._source_id}:{self._protecting}:PROT:TRIP?") == "1"

    def clear(self):
        """clear OCP event"""
        self._scpi.send(f"{self._source_id}:{self._protecting}:PROT:CLE")


class OverCurrentProtection(OverProtectiveParent):
    def __init__(self, channel: int, scpi: SCPIClient):
        super().__init__(channel, "CURRent", scpi)


class OverVoltageProtection(OverProtectiveParent):
    def __init__(self, channel: int, scpi: SCPIClient):
        super().__init__(channel, "VOLTage", scpi)


class Channel:
    def __init__(self, channel: int, scpi: SCPIClient):
        self._channel = channel
        self._scpi = scpi
        self._ocp = OverCurrentProtection(channel, scpi)
        self._ovp = OverVoltageProtection(channel, scpi)

    def __repr__(self):
        out = self.output
        probe = self.probe()
        return (f"<CH{self._channel}: "
                f"voltage: {probe.voltage:.3f} V (set: {out.voltage:.3f} V), "
                f"current: {probe.current:.3f} A (set: {out.current:.3f}) A>")

    @contextmanager
    def __call__(self, output: Output):
        try:
            self.output = output
            self.enable()
            yield
        finally:
            self.disable()

    @property
    def output(self) -> Output:
        response = self._scpi.query(f":APPL? CH{self._channel}")
        _, response = response.split(":", maxsplit=1)
        _, set_voltage, set_current = response.split(",")
        return Output(float(set_voltage), float(set_current))

    @output.setter
    def output(self, output: Output):
        output = Output(*output)
        self._scpi.send(f":APPL CH{self._channel},{output.voltage:.3f},"
                        f"{output.current:.3f}")

    def probe(self) -> Measurement:
        """issues a measurement of voltage, current and power"""
        voltage, current, power = self._scpi.query(
            f"MEAS:ALL? CH{self._channel}").split(",")
        return Measurement(float(voltage), float(current), float(power))

    @property
    def enabled(self) -> bool:
        return self._scpi.query(f":OUTP? CH{self._channel}") == "1"

    @enabled.setter
    def enabled(self, value):
        self._scpi.send(
            f":OUTP CH{self._channel},{'ON' if value else 'OFF'}")

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    @property
    def output_mode(self) -> OutputMode:
        # No `@output_mode.setter` implementable. The instrument considers
        # itself in CV mode most of the time, except when it is hitting its
        # current limitation threshold.
        return OutputMode(self._scpi.query(f":OUTP:MODE? CH{self._channel}"))

    @property
    def ocp(self) -> OverCurrentProtection:
        """over-current-protection"""
        return self._ocp

    @property
    def ovp(self) -> OverVoltageProtection:
        """over-voltage-protection"""
        return self._ovp
