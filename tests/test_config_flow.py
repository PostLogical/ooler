"""Tests for the Ooler config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ooler.config_flow import OolerConfigFlow
from custom_components.ooler.const import CONF_MODEL, DOMAIN

from .conftest import OOLER_ADDRESS, OOLER_NAME, make_mock_client, make_service_info


async def test_bluetooth_discovery() -> None:
    """Test bluetooth discovery initializes the flow."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}

    service_info = make_service_info()

    with patch.object(flow, "async_set_unique_id", return_value=None):
        with patch.object(flow, "_abort_if_unique_id_configured"):
            with patch.object(flow, "async_step_bluetooth_confirm") as mock_confirm:
                mock_confirm.return_value = {"type": FlowResultType.FORM}
                result = await flow.async_step_bluetooth(service_info)

    assert flow._discovery_info == service_info
    mock_confirm.assert_called_once()


async def test_bluetooth_discovery_not_ooler() -> None:
    """Test non-Ooler devices are rejected."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}

    service_info = make_service_info(name="NotOoler")

    with patch.object(flow, "async_set_unique_id", return_value=None):
        with patch.object(flow, "_abort_if_unique_id_configured"):
            result = await flow.async_step_bluetooth(service_info)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_confirm_shows_form() -> None:
    """Test bluetooth confirm shows the form."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._discovery_info = make_service_info()

    with patch.object(flow, "_set_confirm_only"):
        result = await flow.async_step_bluetooth_confirm()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"


async def test_bluetooth_confirm_triggers_pairing() -> None:
    """Test confirming discovery triggers pairing verification."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._discovery_info = make_service_info()
    flow._paired = False

    with patch.object(flow, "async_step_wait_for_pairing_mode") as mock_wait:
        mock_wait.return_value = {"type": FlowResultType.SHOW_PROGRESS}
        result = await flow.async_step_bluetooth_confirm(user_input={})

    mock_wait.assert_called_once()


async def test_bluetooth_confirm_already_paired() -> None:
    """Test confirming when already paired creates entry."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow._discovery_info = make_service_info()
    flow._paired = True

    with patch.object(flow, "_create_ooler_entry") as mock_create:
        mock_create.return_value = {"type": FlowResultType.CREATE_ENTRY}
        result = await flow.async_step_bluetooth_confirm(user_input={})

    mock_create.assert_called_once_with(OOLER_NAME)


async def test_verify_connection_success() -> None:
    """Test successful GATT connection verification."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    mock_client = make_mock_client()
    service_info = make_service_info()

    with patch(
        "custom_components.ooler.config_flow.OolerBLEDevice",
        return_value=mock_client,
    ):
        await flow._async_verify_connection(service_info)

    assert flow._paired is True
    mock_client.connect.assert_called_once()
    mock_client.async_poll.assert_called_once()
    mock_client.stop.assert_called_once()


async def test_verify_connection_failure() -> None:
    """Test failed GATT connection verification."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    mock_client = make_mock_client()
    mock_client.connect = AsyncMock(side_effect=TimeoutError)
    service_info = make_service_info()

    with patch(
        "custom_components.ooler.config_flow.OolerBLEDevice",
        return_value=mock_client,
    ):
        await flow._async_verify_connection(service_info)

    assert flow._paired is False
    mock_client.stop.assert_called_once()


async def test_user_flow_no_devices() -> None:
    """Test user flow with no discovered devices aborts."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()

    with patch(
        "custom_components.ooler.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await flow.async_step_user()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_with_devices() -> None:
    """Test user flow shows discovered Ooler devices."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    service_info = make_service_info()

    with patch.object(flow, "_async_current_ids", return_value=set()):
        with patch(
            "custom_components.ooler.config_flow.async_discovered_service_info",
            return_value=[service_info],
        ):
            result = await flow.async_step_user()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_pairing_timeout_retry() -> None:
    """Test pairing timeout step allows retry."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._pairing_task = MagicMock()

    with patch.object(flow, "async_step_wait_for_pairing_mode") as mock_wait:
        mock_wait.return_value = {"type": FlowResultType.SHOW_PROGRESS}
        result = await flow.async_step_pairing_timeout(user_input={})

    assert flow._pairing_task is None
    mock_wait.assert_called_once()


async def test_pairing_timeout_shows_form() -> None:
    """Test pairing timeout shows retry form."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()

    with patch.object(flow, "_set_confirm_only"):
        result = await flow.async_step_pairing_timeout()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pairing_timeout"


async def test_create_entry() -> None:
    """Test _create_ooler_entry creates config entry."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()

    with patch.object(flow, "async_create_entry") as mock_create:
        mock_create.return_value = {
            "type": FlowResultType.CREATE_ENTRY,
            "title": OOLER_NAME,
        }
        flow._create_ooler_entry(OOLER_NAME)

    mock_create.assert_called_once_with(
        title=OOLER_NAME,
        data={CONF_MODEL: OOLER_NAME},
    )


async def test_reconfigure_shows_form() -> None:
    """Test reconfigure step shows the form."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "test_entry_id"}

    mock_entry = MagicMock()
    mock_entry.unique_id = OOLER_ADDRESS
    flow.hass.config_entries.async_get_entry.return_value = mock_entry

    result = await flow.async_step_reconfigure()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"


async def test_reconfigure_triggers_pairing() -> None:
    """Test reconfigure with input triggers pairing verification."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "test_entry_id"}

    mock_entry = MagicMock()
    mock_entry.unique_id = OOLER_ADDRESS
    flow.hass.config_entries.async_get_entry.return_value = mock_entry

    service_info = make_service_info()
    with patch(
        "custom_components.ooler.config_flow.async_last_service_info",
        return_value=service_info,
    ):
        with patch.object(flow, "async_step_wait_for_pairing_mode") as mock_wait:
            mock_wait.return_value = {"type": FlowResultType.SHOW_PROGRESS}
            result = await flow.async_step_reconfigure(user_input={})

    mock_wait.assert_called_once()


async def test_user_flow_select_device() -> None:
    """Test user flow selecting a device triggers pairing."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._discovered_devices = {OOLER_ADDRESS: OOLER_NAME}

    service_info = make_service_info()

    with (
        patch.object(flow, "async_set_unique_id", return_value=None),
        patch.object(flow, "_abort_if_unique_id_configured"),
        patch(
            "custom_components.ooler.config_flow.async_last_service_info",
            return_value=service_info,
        ),
        patch.object(flow, "async_step_wait_for_pairing_mode") as mock_wait,
    ):
        mock_wait.return_value = {"type": FlowResultType.SHOW_PROGRESS}
        result = await flow.async_step_user(
            user_input={"address": OOLER_ADDRESS}
        )

    mock_wait.assert_called_once()


async def test_user_flow_select_device_already_paired() -> None:
    """Test user flow with already paired device creates entry."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._discovered_devices = {OOLER_ADDRESS: OOLER_NAME}
    flow._paired = True

    service_info = make_service_info()

    with (
        patch.object(flow, "async_set_unique_id", return_value=None),
        patch.object(flow, "_abort_if_unique_id_configured"),
        patch(
            "custom_components.ooler.config_flow.async_last_service_info",
            return_value=service_info,
        ),
        patch.object(flow, "_create_ooler_entry") as mock_create,
    ):
        mock_create.return_value = {"type": FlowResultType.CREATE_ENTRY}
        result = await flow.async_step_user(
            user_input={"address": OOLER_ADDRESS}
        )

    mock_create.assert_called_once_with(OOLER_NAME)


async def test_user_flow_select_none_model() -> None:
    """Test user flow aborts when model_name is None."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._discovered_devices = {OOLER_ADDRESS: None}

    with (
        patch.object(flow, "async_set_unique_id", return_value=None),
        patch.object(flow, "_abort_if_unique_id_configured"),
    ):
        result = await flow.async_step_user(
            user_input={"address": OOLER_ADDRESS}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_filters_configured_and_non_ooler() -> None:
    """Test user flow filters out configured and non-Ooler devices."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()

    ooler_info = make_service_info()
    non_ooler = make_service_info(address="AA:BB:CC:DD:EE:FF", name="NotOoler")

    with (
        patch.object(flow, "_async_current_ids", return_value={OOLER_ADDRESS}),
        patch(
            "custom_components.ooler.config_flow.async_discovered_service_info",
            return_value=[ooler_info, non_ooler],
        ),
    ):
        result = await flow.async_step_user()

    # Both filtered: ooler is already configured, non-ooler has wrong name
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_wait_for_pairing_starts_task() -> None:
    """Test wait_for_pairing creates task and shows progress on first call."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._discovery_info = make_service_info()
    flow._pairing_task = None

    mock_task = MagicMock()
    flow.hass.async_create_task.side_effect = (
        lambda coro, **kw: (coro.close(), mock_task)[1]
    )

    with patch.object(flow, "async_show_progress") as mock_progress:
        mock_progress.return_value = {"type": FlowResultType.SHOW_PROGRESS}
        result = await flow.async_step_wait_for_pairing_mode()

    flow.hass.async_create_task.assert_called_once()
    mock_progress.assert_called_once_with(
        step_id="wait_for_pairing_mode",
        progress_action="wait_for_pairing_mode",
        progress_task=mock_task,
    )
    assert flow._pairing_task == mock_task


async def test_wait_for_pairing_no_discovery_info() -> None:
    """Test wait for pairing shows timeout when no discovery info."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._discovery_info = None

    with patch.object(flow, "async_show_progress_done") as mock_done:
        mock_done.return_value = {"next_step_id": "pairing_timeout"}
        result = await flow.async_step_wait_for_pairing_mode()

    mock_done.assert_called_once_with(next_step_id="pairing_timeout")


async def test_wait_for_pairing_existing_task_success() -> None:
    """Test wait_for_pairing with completed successful task."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._paired = True

    async def noop() -> None:
        pass

    flow._pairing_task = noop()

    with patch.object(flow, "async_show_progress_done") as mock_done:
        mock_done.return_value = {"next_step_id": "pairing_complete"}
        result = await flow.async_step_wait_for_pairing_mode()

    mock_done.assert_called_once_with(next_step_id="pairing_complete")
    assert flow._pairing_task is None


async def test_wait_for_pairing_existing_task_failure() -> None:
    """Test wait_for_pairing with completed failed task."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._paired = False

    async def noop() -> None:
        pass

    flow._pairing_task = noop()

    with patch.object(flow, "async_show_progress_done") as mock_done:
        mock_done.return_value = {"next_step_id": "pairing_timeout"}
        result = await flow.async_step_wait_for_pairing_mode()

    mock_done.assert_called_once_with(next_step_id="pairing_timeout")


async def test_wait_for_pairing_existing_task_cancelled() -> None:
    """Test wait_for_pairing with cancelled task."""
    import asyncio

    flow = OolerConfigFlow()
    flow.hass = MagicMock()

    async def raise_cancelled() -> None:
        raise asyncio.CancelledError

    flow._pairing_task = raise_cancelled()

    with patch.object(flow, "async_show_progress_done") as mock_done:
        mock_done.return_value = {"next_step_id": "pairing_timeout"}
        result = await flow.async_step_wait_for_pairing_mode()

    mock_done.assert_called_once_with(next_step_id="pairing_timeout")
    assert flow._pairing_task is None


async def test_pairing_complete_creates_entry() -> None:
    """Test pairing_complete step creates the config entry."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow._discovery_info = make_service_info()

    with (
        patch.object(flow, "async_set_unique_id", return_value=None),
        patch.object(flow, "_abort_if_unique_id_configured"),
        patch.object(flow, "_create_ooler_entry") as mock_create,
    ):
        mock_create.return_value = {"type": FlowResultType.CREATE_ENTRY}
        result = await flow.async_step_pairing_complete()

    mock_create.assert_called_once_with(OOLER_NAME)


async def test_reconfigure_no_device() -> None:
    """Test reconfigure aborts when device not found."""
    flow = OolerConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "test_entry_id"}

    mock_entry = MagicMock()
    mock_entry.unique_id = OOLER_ADDRESS
    flow.hass.config_entries.async_get_entry.return_value = mock_entry

    with patch(
        "custom_components.ooler.config_flow.async_last_service_info",
        return_value=None,
    ):
        result = await flow.async_step_reconfigure(user_input={})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"
