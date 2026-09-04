from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method


BLUEZ_SERVICE = "org.bluez"
ADV_IFACE = "org.bluez.LEAdvertisement1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHR_IFACE = "org.bluez.GattCharacteristic1"
OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"


def _json_event(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)


def _safe_path_segment(value: str) -> str:
    segment = "".join(ch if ch.isalnum() else "_" for ch in value)
    return segment[:96] or "session"


def _exception_payload(exc: Exception) -> dict[str, str]:
    payload = {"message": str(exc), "exception_type": exc.__class__.__name__}
    dbus_type = getattr(exc, "type", None)
    dbus_text = getattr(exc, "text", None)
    if dbus_type:
        payload["dbus_error"] = str(dbus_type)
    if dbus_text:
        payload["dbus_text"] = str(dbus_text)
    return payload


def _variant_props(props: dict[str, Any]) -> dict[str, Variant]:
    variants: dict[str, Variant] = {}
    for key, value in props.items():
        if isinstance(value, bool):
            variants[key] = Variant("b", value)
        elif isinstance(value, str):
            variants[key] = Variant("s", value)
        elif isinstance(value, list):
            variants[key] = Variant("as", value)
        else:
            variants[key] = value
    return variants


class PairingAdvertisement(ServiceInterface):
    def __init__(self, service_uuid: str, local_name: str, manufacturer_company_id: int, manufacturer_data: bytes) -> None:
        super().__init__(ADV_IFACE)
        self._service_uuid = service_uuid
        self._local_name = local_name
        self._manufacturer_company_id = manufacturer_company_id
        self._manufacturer_data = manufacturer_data
        self.released = asyncio.Event()

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":
        return [self._service_uuid]

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":
        return self._local_name

    @dbus_property(access=PropertyAccess.READ)
    def Discoverable(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def ManufacturerData(self) -> "a{qv}":
        return {self._manufacturer_company_id: Variant("ay", self._manufacturer_data)}

    @method()
    def Release(self):
        self.released.set()


class GattApplication(ServiceInterface):
    def __init__(self, objects: dict[str, dict[str, dict[str, Variant]]]) -> None:
        super().__init__(OBJECT_MANAGER_IFACE)
        self._objects = objects

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":
        return self._objects


class PairingService(ServiceInterface):
    def __init__(self, path: str, service_uuid: str) -> None:
        super().__init__(GATT_SERVICE_IFACE)
        self.path = path
        self._service_uuid = service_uuid

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._service_uuid

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Includes(self) -> "ao":
        return []


class PairingCharacteristic(ServiceInterface):
    def __init__(
        self,
        *,
        path: str,
        uuid: str,
        service_path: str,
        flags: list[str],
        read_value: bytes | None = None,
        identity_path: Path | None = None,
        credential_path: Path | None = None,
    ) -> None:
        super().__init__(GATT_CHR_IFACE)
        self.path = path
        self._uuid = uuid
        self._service_path = service_path
        self._flags = flags
        self._read_value = read_value
        self._identity_path = identity_path
        self._credential_path = credential_path

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return self._service_path

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return self._flags

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        del options
        if self._credential_path is not None:
            if not self._credential_path.exists():
                return json.dumps(
                    {"status": "pending", "error": "ble_pairing_credentials_pending"},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            return self._credential_path.read_bytes()
        return self._read_value or b""

    @method()
    def WriteValue(self, value: "ay", options: "a{sv}"):
        del options
        if self._identity_path is None:
            return
        raw = bytes(value)
        identity = json.loads(raw.decode("utf-8"))
        if not isinstance(identity, dict):
            raise ValueError("identity payload must be a JSON object")
        payload = {"received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "identity": identity}
        self._identity_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._identity_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, self._identity_path)


async def _run(request: dict[str, Any]) -> None:
    adapter = str(request.get("adapter") or "hci0")
    service_uuid = str(request["service_uuid"])
    local_name = str(request.get("local_name") or "HexePair")
    manufacturer_company_id = int(request.get("manufacturer_company_id") or 0xFFFF)
    manufacturer_data = base64.b64decode(str(request["manufacturer_data_b64"]))
    pairing_offer = request["pairing_offer"]
    identity_path = Path(str(request["identity_path"]))
    credential_path = Path(str(request["credential_path"]))
    timeout_s = max(1, int(request.get("timeout_s") or 300))
    onboarding_session_id = str(pairing_offer["onboarding_session_id"])
    segment = _safe_path_segment(onboarding_session_id)

    root_path = f"/com/hexe/pairing/{segment}"
    adv_path = f"{root_path}/advertisement0"
    service_path = f"{root_path}/service0"
    offer_path = f"{service_path}/char0"
    identity_path_obj = f"{service_path}/char1"
    credential_path_obj = f"{service_path}/char2"
    pairing_offer_json = json.dumps(pairing_offer, sort_keys=True, separators=(",", ":")).encode("utf-8")

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    adapter_path = f"/org/bluez/{adapter}"
    introspection = await bus.introspect(BLUEZ_SERVICE, adapter_path)
    adapter_obj = bus.get_proxy_object(BLUEZ_SERVICE, adapter_path, introspection)
    adv_manager = adapter_obj.get_interface("org.bluez.LEAdvertisingManager1")
    gatt_manager = adapter_obj.get_interface("org.bluez.GattManager1")

    service = PairingService(service_path, service_uuid)
    offer_char = PairingCharacteristic(
        path=offer_path,
        uuid="7f9c0000-5f04-4d8b-9a46-7c0f7a100002",
        service_path=service_path,
        flags=["read"],
        read_value=pairing_offer_json,
    )
    identity_char = PairingCharacteristic(
        path=identity_path_obj,
        uuid="7f9c0000-5f04-4d8b-9a46-7c0f7a100001",
        service_path=service_path,
        flags=["write", "write-without-response"],
        identity_path=identity_path,
    )
    credential_char = PairingCharacteristic(
        path=credential_path_obj,
        uuid="7f9c0000-5f04-4d8b-9a46-7c0f7a100004",
        service_path=service_path,
        flags=["read"],
        credential_path=credential_path,
    )
    objects = {
        service_path: {
            GATT_SERVICE_IFACE: _variant_props(
                {"UUID": service_uuid, "Primary": True, "Includes": Variant("ao", [])}
            )
        },
        offer_path: {
            GATT_CHR_IFACE: _variant_props(
                {"UUID": offer_char.UUID, "Service": Variant("o", service_path), "Flags": offer_char.Flags}
            )
        },
        identity_path_obj: {
            GATT_CHR_IFACE: _variant_props(
                {"UUID": identity_char.UUID, "Service": Variant("o", service_path), "Flags": identity_char.Flags}
            )
        },
        credential_path_obj: {
            GATT_CHR_IFACE: _variant_props(
                {"UUID": credential_char.UUID, "Service": Variant("o", service_path), "Flags": credential_char.Flags}
            )
        },
    }
    app = GattApplication(objects)
    advert = PairingAdvertisement(service_uuid, local_name, manufacturer_company_id, manufacturer_data)
    bus.export(root_path, app)
    bus.export(service_path, service)
    bus.export(offer_path, offer_char)
    bus.export(identity_path_obj, identity_char)
    bus.export(credential_path_obj, credential_char)
    bus.export(adv_path, advert)

    registered_gatt = False
    registered_adv = False
    try:
        await gatt_manager.call_register_application(root_path, {})
        registered_gatt = True
        await adv_manager.call_register_advertisement(adv_path, {})
        registered_adv = True
        _json_event(
            {
                "ok": True,
                "event": "started",
                "adapter": adapter,
                "local_name": local_name,
                "onboarding_session_id": onboarding_session_id,
                "service_uuid": service_uuid,
                "timeout_s": timeout_s,
            }
        )
        try:
            await asyncio.wait_for(advert.released.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            pass
    finally:
        if registered_adv:
            try:
                await adv_manager.call_unregister_advertisement(adv_path)
            except Exception:
                pass
        if registered_gatt:
            try:
                await gatt_manager.call_unregister_application(root_path)
            except Exception:
                pass


def main() -> int:
    if len(sys.argv) != 2:
        _json_event({"ok": False, "error": "invalid_arguments"})
        return 2
    try:
        request = json.loads(sys.argv[1])
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, loop.stop)
        loop.run_until_complete(_run(request))
        return 0
    except Exception as exc:
        _json_event({"ok": False, "error": "ble_pairing_advert_bluez_failed", **_exception_payload(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
