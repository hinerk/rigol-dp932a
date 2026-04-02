from contextlib import contextmanager
from collections import namedtuple
from enum import Enum
from tcp_scpi import SCPIClient
from typing import Literal, TypeAlias
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .rigol_dp932a import RigolDP932A

Volt: TypeAlias = float
Ampere: TypeAlias = float

logger = logging.getLogger(__name__)


class OutputMode(Enum):
    ConstantVoltage = "CV"
    ConstantCurrent = "CV"
    Unregulated = "UR"


Measurement = namedtuple("Measurement", ["voltage", "current", "power"])
Output = namedtuple("Output", ["voltage", "current"])


class OverProtectiveParent:
    # fraction of the SCPI command which specifies the kind of protection
    _protecting: Literal["CURRent", "VOLTage"]

    # referring name in log messages
    _desc: str

    # how to refer to self in the repr
    _repr: str

    # Unit of the threshold
    _unit: str

    def __init__(
            self,
            channel: "Channel",
            scpi: SCPIClient,
    ):
        self._channel = channel
        self._scpi = scpi
        self._source_id = f":SOURCe[{self._channel.channel_index}]"

    @contextmanager
    def __call__(self, level: float):
        try:
            self.clear()
            self.level = level
            self.enable()
            yield self
        finally:
            self.disable()
            self.clear()

    def __repr__(self):
        return f"{self._channel!r}.{self._repr}"

    @property
    def level(self) -> float:
        """threshold level at which the protection triggers"""
        level = float(self._scpi.query(
            f"{self._source_id}:{self._protecting}:PROT?"))
        logger.info("%r %s threshold is currently at %f%s",
                    self, self._desc, level, self._unit)
        return level

    @level.setter
    def level(self, value: float):
        logger.info("%r set %s threshold to %f%s",
                    self, self._desc, value, self._unit)
        self._scpi.send(
            f"{self._source_id}:{self._protecting}:PROT {value:.3f}")

    @property
    def tripped(self) -> bool:
        """whether the current protection tripped"""
        tripped = self._scpi.query(
            f"{self._source_id}:{self._protecting}:PROT:TRIP?").strip() == "1"
        logger.info("%r %s %s!", self, self._desc,
                    "tripped" if tripped else "hasn't tripped yet")
        return tripped

    @property
    def enabled(self) -> bool:
        """whether the protection is enabled"""
        enabled = self._scpi.query(
            f"{self._source_id}:{self._protecting}:PROT:STAT?").strip() == "1"
        logger.info("%r %s is %s", self, self._desc, "enabled" if enabled else "disabled")
        return enabled

    @enabled.setter
    def enabled(self, value):
        logger.info("%r %s %s", self, "enabling" if value else "disabling",
                    self._desc)
        self._scpi.send(
            f"{self._source_id}:{self._protecting}:PROT:STAT "
            f"{'ON' if value else 'OFF'}")

    def enable(self):
        """enable protection"""
        self.enabled = True

    def disable(self):
        """disable protection"""
        self.enabled = False

    def clear(self):
        """clear OCP event"""
        self._scpi.send(f"{self._source_id}:{self._protecting}:PROT:CLE")


class OverCurrentProtection(OverProtectiveParent):
    _protecting = "CURRent"
    _desc = "OCP"
    _repr = "ocp"
    _unit = "A"


class OverVoltageProtection(OverProtectiveParent):
    _protecting = "VOLTage"
    _desc = "OVP"
    _repr = "ovp"
    _unit = "V"


class Channel:
    def __init__(self, channel: int, scpi: SCPIClient, parent: "RigolDP932A"):
        self._parent = parent
        self._channel = channel
        self._scpi = scpi
        self._ocp = OverCurrentProtection(self, scpi)
        self._ovp = OverVoltageProtection(self, scpi)

    def __repr__(self):
        return f"{self._parent!r}.ch{self._channel}"

    @contextmanager
    def __call__(self, output: Output):
        try:
            self.output = output
            self.enable()
            yield self
        finally:
            self.disable()

    @property
    def output(self) -> Output:
        response = self._scpi.query(f":APPL? CH{self._channel}")
        _, response = response.split(":", maxsplit=1)
        _, set_voltage, set_current = response.split(",")
        volt, curr = float(set_voltage), float(set_current)
        logger.info("%r is set to %fV, %fA")
        return Output(volt, curr)

    @output.setter
    def output(self, output: Output | tuple[Volt, Ampere]):
        output = Output(*output)
        self._scpi.send(f":APPL CH{self._channel},{output.voltage:.3f},"
                        f"{output.current:.3f}")

    def probe(self) -> Measurement:
        """issues a measurement of voltage, current and power"""
        voltage, current, power = self._scpi.query(
            f"MEAS:ALL? CH{self._channel}").split(",")
        voltage, current, power = float(voltage), float(current), float(power)
        measurement = Measurement(voltage, current, power)
        logger.info("%r measured %r", self, measurement)
        return measurement

    @property
    def enabled(self) -> bool:
        enabled = self._scpi.query(f":OUTP? CH{self._channel}").strip() == "1"
        logger.info("%r output is %s", self, "on" if enabled else "off")
        return enabled

    @enabled.setter
    def enabled(self, value):
        logger.info("%r %s output", self._channel, "enable" if value else "disable")
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

    @property
    def channel_index(self):
        return self._channel
