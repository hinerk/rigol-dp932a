from logging import getLogger
from tcp_scpi import SCPIClient
from tcp_scpi import SCPIError
import time

from .analyzer import AnalyzerAPI
from .channel import Channel


logger = getLogger(__name__)


class RigolDP932A:
    command_termination = b'\n'
    error_cmd = ':SYSTem:ERRor?'
    no_error_msg = '0,"No error"'

    def __init__(
            self,
            host: str,
            port: int = 5555,
    ):
        self._host = host
        self._port = port
        self._scpi = SCPIClient(
            host=self._host,
            port=self._port,
            command_termination=self.command_termination,
            error_cmd=self.error_cmd,
            no_error_msg=self.no_error_msg,
        )
        self._idn: str | None = None

        with self._scpi as scpi:
            try:
                error, idn, passed_self_test = scpi.query(
                    f"{self.error_cmd};*IDN?;*TST?",
                    fetch_errors=False,
                ).split(";")
                if error.strip() != self.no_error_msg:
                    logger.error(f"{self!r}: device has remaining errors in "
                                 f"queue: {error!r}!")
                if passed_self_test.strip() != "0":
                    logger.error(f"{self!r}: device didn't pass self test!")
                logger.debug(f"connected to {self._idn!r}")
            except SCPIError as e:
                logger.error(f"failed querying IDN of device due to "
                             f"scpi error: {e!r}")

        self._ch1 = Channel(1, self._scpi)
        self._ch2 = Channel(2, self._scpi)
        self._ch3 = Channel(3, self._scpi)
        self._analyzer = AnalyzerAPI(self._scpi)

    def __enter__(self):
        self._scpi.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._scpi.close()

    def __repr__(self):
        return (f"{self.__class__.__name__}(host={self._host!r}, "
                f"port={self._port!r})")

    def query(self, cmd: str) -> str:
        return self._scpi.query(cmd)

    def send(self, cmd: str, fetch_errors: bool = True) -> str:
        return self._scpi.send(cmd, fetch_errors=fetch_errors)

    @property
    def passed_self_test(self) -> bool:
        return self._scpi.query("*TST?") == "0"

    @property
    def ch1(self) -> Channel:
        return self._ch1

    @property
    def ch2(self) -> Channel:
        return self._ch2

    @property
    def ch3(self) -> Channel:
        return self._ch3

    @property
    def analyzer(self) -> AnalyzerAPI:
        return self._analyzer

    @property
    def display_brightness(self):
        return int(self._scpi.query(":SYST:BRIG?"))

    @display_brightness.setter
    def display_brightness(self, brightness: int):
        self._scpi.send(f":SYST:BRIG {brightness}")

    @property
    def beeper(self):
        return self._scpi.query(":SYST:BEEP?") == "1"

    @beeper.setter
    def beeper(self, value: bool):
        self._scpi.send(
            f":SYST:BEEP {'ON' if value else 'OFF'}")

    def beep(self):
        self._scpi.send(f":SYSTem:BEEPer:IMMediate")

    def look_at_me(self):
        initial_brightness = self.display_brightness
        initial_beeper = self.beeper

        def blink(half_duration = 0.5):
            self.display_brightness = 100
            time.sleep(0.5)
            self.display_brightness = 10
            time.sleep(0.5)

        for _ in range(3):
            blink()
            self.beep()
            blink()

        self.display_brightness = initial_brightness
        self.beeper = initial_beeper
