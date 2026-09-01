from core.config import PipelineConfig, YunyingMediaConfig


def test_media_config_uses_requested_safe_defaults():
    config = PipelineConfig()
    assert isinstance(config.media, YunyingMediaConfig)
    assert config.media.base_url == "https://wy6688.token6688.com/v1"
    assert config.media.video_model == "seedance-2-0-official"
    assert config.media.image_model == "gpt-image-2-official"
    assert config.media.timeout == 4500


def test_yunying_environment_overrides_are_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv("YUNYING_API_KEY", "env-key")
    monkeypatch.setenv("YUNYING_BASE_URL", "https://custom.example/v1")
    monkeypatch.setenv("YUNYING_VIDEO_MODEL", "seedance-2-0-promo")
    monkeypatch.setenv("YUNYING_IMAGE_MODEL", "gpt-image-2")
    from core.config import load_config

    config = load_config(
        config_path=str(tmp_path / "missing.yaml"),
        env_path=str(tmp_path / "missing.env"),
        base_dir=str(tmp_path),
    )
    assert config.media.api_key == "env-key"
    assert config.media.base_url == "https://custom.example/v1"
    assert config.media.video_model == "seedance-2-0-promo"
    assert config.media.image_model == "gpt-image-2"
