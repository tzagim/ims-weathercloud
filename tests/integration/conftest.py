"""Home Assistant test fixtures (needs pytest-homeassistant-custom-component)."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ims_weathercloud."""
    yield
