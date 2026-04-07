from node_template.config.settings import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.node_name == "node-template"
    assert settings.api_port == 9000
