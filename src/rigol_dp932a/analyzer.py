from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from tcp_scpi import SCPIClient


class AnalysisType(Enum):
    Common = "COM"
    PulseCurrent = "CURR"


class CommonAnalysisType(Enum):
    Voltage = "V"
    Current = "C"
    Power = "P"

@dataclass
class CommonAnalysis:
    ch1: Optional[CommonAnalysisType] = None
    ch2: Optional[CommonAnalysisType] = None
    ch3: Optional[CommonAnalysisType] = None


@dataclass
class PulseCurrentAnalysis:
    ch1: bool = True
    ch2: bool = True


class AnalyzerAPI:
    def __init__(self, scpi_client: SCPIClient):
        self._scpi_client = scpi_client

    @property
    def log(self) -> bool:
        """Queries whether the analyzer is currently logging to a file"""
        return self._scpi_client.query(":ANALyzer:SAVE:STATe?")

    @log.setter
    def log(self, enabled: bool):
        """enables the logging of the analyzer"""
        self._scpi_client.send(
            f":ANALyzer:SAVE:STATe {'1' if enabled else '0'}")

    @property
    def active(self) -> bool:
        """Queries the on/off state of the analyzer"""
        return self._scpi_client.query(":ANALyzer:STATe?") == "1"

    @active.setter
    def active(self, enabled: bool):
        """Turns on the analyzer."""
        self._scpi_client.send(f":ANALyzer:STATe {'1' if enabled else '0'}")

    @property
    def file(self) -> str:
        """Queries the path where the log file is currently saved"""
        return self._scpi_client.query(":ANALyzer:SAVE:ROUTe?")

    @file.setter
    def file(self, file: str):
        """Sets the current saved path of the log file"""
        self._scpi_client.send(f":ANALyzer:SAVE:ROUTe {file}")

    @property
    def type(self) -> AnalysisType:
        return AnalysisType(self._scpi_client.query(":ANALyzer:TYPE?"))

    @type.setter
    def type(self, analysis_type: AnalysisType):
        self._scpi_client.send(f":ANALyzer:TYPE {analysis_type.value}")

    def get_common_measure(self) -> CommonAnalysis:
        response = self._scpi_client.query(":ANALyzer:COMMon:MEASure:TYPE?")
        result = CommonAnalysis()
        for item in response.split(" "):
            channel, analysis_type = item.split("_")
            if channel == "CH1":
                result.ch1 = CommonAnalysisType(analysis_type)
            elif channel == "CH2":
                result.ch2 = CommonAnalysisType(analysis_type)
            elif channel == "CH3":
                result.ch3 = CommonAnalysisType(analysis_type)
            else:
                raise AssertionError("Hinerk assumed he knew how to code!")
        return result

    def set_common_measure(
            self,
            config: CommonAnalysis,
    ):
        self.type = AnalysisType.Common
        cmd_parts = []
        for i, ch in enumerate([config.ch1, config.ch2, config.ch3], start=1):
            if ch is not None:
                cmd_parts.append(f"CH{i}_{ch.value}")
        cmd = ','.join(cmd_parts)
        self._scpi_client.send(f":ANALyzer:COMMon:MEASure:TYPE {cmd}")

    def get_current_measure(self):
        return self._scpi_client.send(":ANALyzer:CURRent:MEASure:TYPE?")

    def set_current_measure(self, config: PulseCurrentAnalysis):
        self.type = AnalysisType.PulseCurrent
        if not any([config.ch1, config.ch2]):
            raise AttributeError("Pulse-Current-Analysis requires at least "
                                 "one enabled channel!")
        cmd = ','.join([
            f"CH{i}"
            for i, ch in enumerate([config.ch1, config.ch2], start=1)
            if ch
        ])
        self._scpi_client.send(f":ANALyzer:CURRent:MEASure:TYPE {cmd}")

    @contextmanager
    def analyze(
            self,
            config: CommonAnalysis | PulseCurrentAnalysis,
            log: bool = False,
    ):
        initial_value_of_self_log = self.log
        initial_value_of_self_active = self.active
        try:
            if isinstance(config, PulseCurrentAnalysis):
                self.set_current_measure(config)
            else:
                self.set_common_measure(config)
            if log:
                self.log = True
            self.active = True
            yield
        finally:
            self.active = initial_value_of_self_active
            if log:
                self.log = initial_value_of_self_log
