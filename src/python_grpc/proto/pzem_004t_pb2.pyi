from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ReadingReport(_message.Message):
    __slots__ = ("device_id", "device_type", "timestamp_unix_ms", "voltage", "current", "active_power", "energy", "frequency", "power_factor")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TYPE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_UNIX_MS_FIELD_NUMBER: _ClassVar[int]
    VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_POWER_FIELD_NUMBER: _ClassVar[int]
    ENERGY_FIELD_NUMBER: _ClassVar[int]
    FREQUENCY_FIELD_NUMBER: _ClassVar[int]
    POWER_FACTOR_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    device_type: str
    timestamp_unix_ms: int
    voltage: float
    current: float
    active_power: float
    energy: float
    frequency: float
    power_factor: float
    def __init__(self, device_id: _Optional[str] = ..., device_type: _Optional[str] = ..., timestamp_unix_ms: _Optional[int] = ..., voltage: _Optional[float] = ..., current: _Optional[float] = ..., active_power: _Optional[float] = ..., energy: _Optional[float] = ..., frequency: _Optional[float] = ..., power_factor: _Optional[float] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ("success", "message", "received_at_unix_ms")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RECEIVED_AT_UNIX_MS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    received_at_unix_ms: int
    def __init__(self, success: _Optional[bool] = ..., message: _Optional[str] = ..., received_at_unix_ms: _Optional[int] = ...) -> None: ...

class BatchSummary(_message.Message):
    __slots__ = ("received", "rejected", "avg_active_power")
    RECEIVED_FIELD_NUMBER: _ClassVar[int]
    REJECTED_FIELD_NUMBER: _ClassVar[int]
    AVG_ACTIVE_POWER_FIELD_NUMBER: _ClassVar[int]
    received: int
    rejected: int
    avg_active_power: float
    def __init__(self, received: _Optional[int] = ..., rejected: _Optional[int] = ..., avg_active_power: _Optional[float] = ...) -> None: ...

class SubscribeRequest(_message.Message):
    __slots__ = ("device_id",)
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    def __init__(self, device_id: _Optional[str] = ...) -> None: ...
