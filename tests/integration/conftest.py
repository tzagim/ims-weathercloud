"""Home Assistant test fixtures (needs pytest-homeassistant-custom-component)."""
import pytest

# Import this repo's custom_components now, at collection time. Home Assistant
# imports the package named "custom_components" once, when the first test
# instance starts, and the test harness ships its own; whichever is imported
# first wins. Without this, a test file that doesn't import the integration
# itself (run alone) would get the harness's copy and not find ours.
import custom_components.ims_weathercloud  # noqa: F401,E402


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ims_weathercloud."""
    yield
