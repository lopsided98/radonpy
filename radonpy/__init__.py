import abc
import asyncio
import datetime
import logging
import struct
import time
from dataclasses import dataclass
from enum import IntEnum
from types import TracebackType
from typing import AsyncGenerator, Optional, Sequence, Type, TypeVar, cast, overload

import bleak
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

_logger = logging.getLogger(__name__)


class Command(IntEnum):
    MEAS_QUERY = 0x50
    BLE_STATUS_QUERY = 0x51
    BLE_RD200_DATE_TIME_SET = 0xA1
    BLE_RD200_UNIT_SET = 0xA2
    SN_QUERY = 0xA4
    SN_TYPE_QUERY = 0xA6
    MODEL_NAME_RETURN = 0xA8
    BLE_WARNING_SET = 0xAA
    CONFIG_QUERY = 0xAC
    OLED_QUERY = 0xAD  # Doesn't seem to work
    BLE_VERSION_QUERY = 0xAF
    MOD_CONFIG_QUERY = 0xB1
    MOD_PROTECTION_RETURN = 0xB3
    MOD_PROTECTION_QUERY = 0xB4
    DISPLAY_CAL_FACTOR_QUERY = 0xBD
    PRODUCT_PROCESS_MODE_QUERY = 0xC1
    EEPROM_LONG_DATA_CLEAR = 0xE0
    EEPROM_LOG_INFO_QUERY = 0xE8
    EEPROM_LOG_DATA_SEND = 0xE9


class Unit(IntEnum):
    """pCi/L"""

    PCI_L = 0
    """Bq/m^3"""
    BQ_M3 = 1


class AlarmInterval(IntEnum):
    TEN_MINUTES = 0x1
    ONE_HOUR = 0x6
    SIX_HOURS = 0x24


class SendPacket(abc.ABC):
    SEND_COMMAND: Command

    @abc.abstractmethod
    def pack(self) -> bytes:
        pass


R = TypeVar("R", bound="RecvPacket")


class RecvPacket:
    RECV_COMMAND: Command

    @classmethod
    @abc.abstractmethod
    def unpack(cls: Type[R], data: bytes) -> R:
        pass


_PACKET_DATABASE = dict()


def _register_packet(packet_type: Type[RecvPacket]) -> None:
    _PACKET_DATABASE[packet_type.RECV_COMMAND] = packet_type


@dataclass
class Measurement(RecvPacket):
    RECV_COMMAND = Command.MEAS_QUERY

    read_value: float
    day_value: float
    month_value: float
    pulse_count: int
    pulse_count_10_min: int

    @classmethod
    def unpack(cls, data: bytes) -> Measurement:
        return cls(*struct.unpack("<fffHH", data))


_register_packet(Measurement)


@dataclass
class Status(RecvPacket):
    RECV_COMMAND = Command.BLE_STATUS_QUERY

    device_status: int
    vib_status: int
    proc_time: int
    dc_value: int
    peak_value: float

    @classmethod
    def unpack(cls, data: bytes) -> Status:
        return cls(*struct.unpack("<BBIIf", data))


_register_packet(Status)


@dataclass
class DateTimeSet(SendPacket):
    SEND_COMMAND = Command.BLE_RD200_DATE_TIME_SET

    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int

    def pack(self) -> bytes:
        return bytes((self.year, self.month, self.day, self.hour, self.minute, self.second))


@dataclass
class UnitSet(SendPacket):
    SEND_COMMAND = Command.BLE_RD200_UNIT_SET

    unit: Unit

    def pack(self) -> bytes:
        return bytes((self.unit,))


@dataclass
class Serial(RecvPacket):
    RECV_COMMAND = Command.SN_QUERY

    date: str
    serial: str

    @classmethod
    def unpack(cls, data: bytes) -> Serial:
        date = data[:8].decode("utf-8")
        serial = data[8:].decode("utf-8")
        return cls(date, serial)


_register_packet(Serial)


@dataclass
class SNType(RecvPacket):
    RECV_COMMAND = Command.SN_TYPE_QUERY

    type: str

    @classmethod
    def unpack(cls, data: bytes) -> SNType:
        return cls(data[:3].decode("utf-8"))


_register_packet(SNType)


@dataclass
class ModelName(RecvPacket):
    RECV_COMMAND = Command.MODEL_NAME_RETURN

    """
    Some value with unknown meaning. Not parsed by the Android app.
    """
    val: int
    name: str

    @classmethod
    def unpack(cls, data: bytes) -> ModelName:
        return cls(data[0], data[1:].decode("utf-8"))


_register_packet(ModelName)


@dataclass
class AlarmSet(SendPacket):
    SEND_COMMAND = Command.BLE_WARNING_SET

    status: int
    value: float
    interval: int

    def pack(self) -> bytes:
        return struct.pack("<BfB", self.status, self.value, self.interval)


@dataclass
class Config(RecvPacket):
    RECV_COMMAND = Command.CONFIG_QUERY

    unit: Unit
    alarm_status: int
    alarm_value: float
    alarm_interval: AlarmInterval

    @classmethod
    def unpack(cls, data: bytes) -> Config:
        fields = struct.unpack("<BBfB", data)
        unit = Unit(fields[0])
        interval = AlarmInterval(fields[3])
        return cls(unit, fields[1], fields[2], interval)


_register_packet(Config)


@dataclass
class OLEDConfig(RecvPacket):
    RECV_COMMAND = Command.OLED_QUERY

    value: int

    @classmethod
    def unpack(cls, data: bytes) -> OLEDConfig:
        return cls(*struct.unpack("<I", data))


_register_packet(OLEDConfig)


@dataclass
class FirmwareInfo(RecvPacket):
    RECV_COMMAND = Command.BLE_VERSION_QUERY

    version: str
    status: int

    @classmethod
    def unpack(cls, data: bytes) -> FirmwareInfo:
        version = data[:64].decode("utf-8")
        if len(data) >= 64 + 4:
            status = int.from_bytes(data[64 : 64 + 4], byteorder="little")
        else:
            status = 0
        return cls(version, status)


_register_packet(FirmwareInfo)


@dataclass
class ModuleConfig(RecvPacket):
    RECV_COMMAND = Command.MOD_CONFIG_QUERY

    device_type: int
    sn_date: int
    sn_no: int
    factor: float

    @classmethod
    def unpack(cls, data: bytes) -> ModuleConfig:
        return cls(*struct.unpack("<BIIf", data))


_register_packet(ModuleConfig)


@dataclass
class ModuleProtection(RecvPacket):
    RECV_COMMAND = Command.MOD_PROTECTION_RETURN

    protection_status: int
    operation_status: int

    @classmethod
    def unpack(cls, data: bytes) -> ModuleProtection:
        return cls(*struct.unpack("<II", data))


_register_packet(ModuleProtection)


@dataclass
class DisplayCalFactor(RecvPacket):
    RECV_COMMAND = Command.DISPLAY_CAL_FACTOR_QUERY

    factor: float

    @classmethod
    def unpack(cls, data: bytes) -> DisplayCalFactor:
        return cls(*struct.unpack("<f", data))


_register_packet(DisplayCalFactor)


@dataclass
class ProductProcessMode(RecvPacket):
    RECV_COMMAND = Command.PRODUCT_PROCESS_MODE_QUERY

    on_off: int
    time_hour: int
    bq: int

    @classmethod
    def unpack(cls, data: bytes) -> ProductProcessMode:
        return cls(*struct.unpack("<BBH", data))


_register_packet(ProductProcessMode)


@dataclass
class LogInfo(RecvPacket):
    RECV_COMMAND = Command.EEPROM_LOG_INFO_QUERY

    data_no: int
    checksum: int

    @staticmethod
    def unpack(data: bytes) -> LogInfo:
        # Unknown extra data at the end
        return LogInfo(*struct.unpack("<Hb", data[:3]))


_register_packet(LogInfo)


class RD200:
    """
    RadonEye uses the Nordic LED Button Service, which suggests that they were
    lazy and just modified some example code without even bothering to change
    the UUIDs.
    """

    LBS_UUID_SERVICE = "00001523-1212-efde-1523-785feabcd123"
    LBS_UUID_CONTROL = "00001524-1212-efde-1523-785feabcd123"
    LBS_UUID_MEAS = "00001525-1212-efde-1523-785feabcd123"
    LBS_UUID_LOG = "00001526-1212-efde-1523-785feabcd123"

    def __init__(self, *args: object, adapter: Optional[str] = None, **kwargs: object):
        """
        Initialization of an instance of a remote RadonEye RD200
        :param address_or_ble_device: The Bluetooth address of the BLE
        peripheral to connect to or the `BLEDevice` object representing it.
        """

        # Can't pass adapter=None to BleakClient
        if adapter is not None:
            kwargs.update(adapter=adapter)

        self.device = bleak.BleakClient(*args, **kwargs)

        self._ctl: Optional[BleakGATTCharacteristic] = None
        self._meas: Optional[BleakGATTCharacteristic] = None
        self._log: Optional[BleakGATTCharacteristic] = None

    async def __aenter__(self) -> "RD200":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        return await self.disconnect()

    @classmethod
    async def discover(
        cls, timeout: float = 5.0, adapter: Optional[str] = None, **kwargs: object
    ) -> AsyncGenerator[BLEDevice, None]:
        """
        Generator to discover RadonEye RD200 devices
        :return: BLEDevice objects
        """

        device_queue = asyncio.Queue[BLEDevice]()

        def detection_callback(d: BLEDevice, ad: Optional[AdvertisementData]) -> None:
            if "uuids" in d.metadata:
                uuids = d.metadata["uuids"]
            elif ad is not None:
                uuids = ad.service_uuids
            else:
                return
            if RD200.LBS_UUID_SERVICE in uuids:
                device_queue.put_nowait(d)

        # Can't pass adapter=None to BleakScanner
        if adapter is not None:
            kwargs.update(adapter=adapter)

        async with bleak.BleakScanner(detection_callback=detection_callback, **kwargs) as scanner:
            for device in await scanner.get_discovered_devices():
                detection_callback(device, None)
            start_time = time.time()
            while True:
                yield await asyncio.wait_for(
                    device_queue.get(), timeout - (time.time() - start_time)
                )

    @property
    def address(self) -> str:
        """Read the device's Bluetooth address"""
        return cast(str, self.device.address)

    @property
    async def connected(self) -> bool:
        """Indicate whether the remote device is currently connected."""
        return cast(bool, await self.device.is_connected())

    async def connect(self) -> bool:
        """
        Connect to the RadonEye device.
        """
        if not await self.device.connect():
            return False

        service = (await self.device.get_services()).get_service(self.LBS_UUID_SERVICE)
        self._ctl = service.get_characteristic(self.LBS_UUID_CONTROL)
        self._meas = service.get_characteristic(self.LBS_UUID_MEAS)
        self._log = service.get_characteristic(self.LBS_UUID_LOG)

        return True

    async def disconnect(self) -> bool:
        """
        Disconnect from the RadonEye device.
        """
        return cast(bool, await self.device.disconnect())

    @property
    async def measurement(self) -> Measurement:
        return await self._request_packet(Command.MEAS_QUERY, Measurement)

    @property
    async def status(self) -> Status:
        return await self._request_packet(Command.BLE_STATUS_QUERY, Status)

    async def set_date_time(self, date: Optional[datetime.datetime] = None) -> None:
        if date is None:
            date = datetime.datetime.now()

        year = int(date.strftime("%y"))
        month = int(date.strftime("%m"))
        day = int(date.strftime("%d"))
        hour = int(date.strftime("%H"))
        minute = int(date.strftime("%M"))
        second = int(date.strftime("%S"))

        await self._send_packet(DateTimeSet(year, month, day, hour, minute, second))

    @property
    async def unit(self) -> Unit:
        return (await self.config).unit

    async def set_unit(self, unit: Unit) -> None:
        await self._send_packet(UnitSet(unit))

    async def alarm(
        self,
        enabled: Optional[bool] = None,
        value: Optional[float] = None,
        interval: Optional[AlarmInterval] = None,
    ) -> None:
        if enabled is None or value is None or interval is None:
            config = await self.config
            if enabled is None:
                enabled = bool(config.alarm_status)
            if value is None:
                value = config.alarm_value
            if interval is None:
                interval = config.alarm_interval
        await self._send_packet(AlarmSet(enabled, value, interval))

    @property
    async def alarm_status(self) -> int:
        return (await self.config).alarm_status

    @property
    async def alarm_value(self) -> float:
        return (await self.config).alarm_value

    @property
    async def alarm_interval(self) -> AlarmInterval:
        return (await self.config).alarm_interval

    @property
    async def config(self) -> Config:
        return await self._request_packet(Command.CONFIG_QUERY, Config)

    @property
    async def serial(self) -> Serial:
        return await self._request_packet(Command.SN_QUERY, Serial)

    @property
    async def serial_type(self) -> str:
        return (await self._request_packet(Command.SN_TYPE_QUERY, SNType)).type

    @property
    async def model_name(self) -> str:
        return (await self._request_packet(Command.MODEL_NAME_RETURN, ModelName)).name

    @property
    async def firmware_info(self) -> FirmwareInfo:
        return await self._request_packet(Command.BLE_VERSION_QUERY, FirmwareInfo)

    @property
    async def module_config(self) -> ModuleConfig:
        return await self._request_packet(Command.MOD_CONFIG_QUERY, ModuleConfig)

    @property
    async def module_protection(self) -> ModuleProtection:
        return await self._request_packet(Command.MOD_PROTECTION_QUERY, ModuleProtection)

    @property
    async def calibration_factor(self) -> float:
        return (
            await self._request_packet(Command.DISPLAY_CAL_FACTOR_QUERY, DisplayCalFactor)
        ).factor

    @property
    async def product_process_mode(self) -> ProductProcessMode:
        return await self._request_packet(Command.PRODUCT_PROCESS_MODE_QUERY, ProductProcessMode)

    @property
    async def log_info(self) -> LogInfo:
        return await self._request_packet(Command.EEPROM_LOG_INFO_QUERY, LogInfo)

    async def get_log(self, timeout: float = 10.0) -> Sequence[float]:
        log_info = await self.log_info

        log_buffer_len = log_info.data_no * 2
        log_buffer_done = asyncio.Event()
        log_buffer = bytearray()

        def log_data_callback(_sender: int, data: bytearray) -> None:
            _logger.debug(f"<-- (LOG) {data.hex()}")
            log_buffer.extend(data)
            if len(log_buffer) >= log_buffer_len:
                log_buffer_done.set()

        await self.device.start_notify(self._log, log_data_callback)
        await self._send_command(Command.EEPROM_LOG_DATA_SEND)
        await asyncio.wait_for(log_buffer_done.wait(), timeout=timeout)
        await self.device.stop_notify(self._log)

        log_data = []
        for i in range(log_info.data_no):
            log_point_raw = int.from_bytes(log_buffer[i * 2 : i * 2 + 2], byteorder="little")
            log_data.append(log_point_raw / 100.0)

        return log_data

    async def _send_command(self, command: Command) -> None:
        buffer = bytearray((command,))
        _logger.debug(f"--> (CTL) {buffer.hex()}")
        await self.device.write_gatt_char(self._ctl, buffer)

    async def _send_packet(self, packet: SendPacket) -> None:
        buffer = bytearray()
        buffer.append(packet.SEND_COMMAND)
        data = packet.pack()
        buffer.append(len(data))
        buffer.extend(data)
        _logger.debug(f"--> (CTL) {buffer.hex()}")

        await self.device.write_gatt_char(self._ctl, buffer)

    @overload
    async def _request_packet(
        self,
        command: Command,
        response_type: Type[R],
        timeout: Optional[float] = None,
    ) -> R:
        pass

    @overload
    async def _request_packet(
        self,
        command: Command,
        response_type: None = None,
        timeout: Optional[float] = None,
    ) -> RecvPacket:
        pass

    async def _request_packet(
        self,
        command: Command,
        response_type: Optional[Type[R]] = None,
        timeout: Optional[float] = None,
    ) -> RecvPacket:
        recv_future = asyncio.Future[bytearray]()

        def meas_callback(_sender: int, data: bytearray) -> None:
            if not recv_future.done():
                recv_future.set_result(data)
            else:
                _logger.warning("received more than one response")

        await self.device.start_notify(self._meas, meas_callback)
        try:
            await self._send_command(command)
            buffer = await asyncio.wait_for(recv_future, timeout)
        finally:
            try:
                # This can fail if the device disconnected, but we should
                # ignore the error in this case
                await self.device.stop_notify(self._meas)
            # All kinds of exceptions can be thrown after the device disconnects
            except BaseException as e:
                _logger.warning("failed to stop notify", exc_info=e)

        return self._parse_packet(buffer)

    @overload
    async def _recv_packet(self, packet_type: Type[R], timeout: Optional[float] = None) -> R:
        pass

    @overload
    async def _recv_packet(
        self, packet_type: None = None, timeout: Optional[float] = None
    ) -> RecvPacket:
        pass

    async def _recv_packet(
        self, packet_type: Optional[Type[R]] = None, timeout: Optional[float] = None
    ) -> RecvPacket:
        recv_future = asyncio.Future[bytearray]()

        def meas_callback(_sender: int, data: bytearray) -> None:
            recv_future.set_result(data)

        try:
            await self.device.start_notify(self._meas, meas_callback)

            buffer = await asyncio.wait_for(recv_future, timeout)
            return self._parse_packet(buffer, packet_type)
        finally:
            await self.device.stop_notify(self._meas)

    @overload
    def _parse_packet(self, buffer: bytearray, packet_type: Type[R]) -> R:
        pass

    @overload
    def _parse_packet(self, buffer: bytearray, packet_type: None = None) -> RecvPacket:
        pass

    def _parse_packet(self, buffer: bytearray, packet_type: Optional[Type[R]] = None) -> RecvPacket:
        command = buffer[0]
        length = buffer[1]
        data = buffer[2 : 2 + length]
        _logger.debug(f"<-- (MEAS) {buffer[:2 + length].hex()}")

        resolved_packet_type: Type[RecvPacket]
        if packet_type is not None:
            if packet_type.RECV_COMMAND != command:
                raise TypeError("Wrong packet type received")
            resolved_packet_type = packet_type
        else:
            resolved_packet_type = _PACKET_DATABASE[Command(command)]

        return resolved_packet_type.unpack(data)
