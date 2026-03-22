"""配置管理 — 通过 .env 和环境变量加载设置。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """VoiceKB 全局配置。"""

    model_config = SettingsConfigDict(env_prefix="VOICEKB_", env_file=".env")

    # ── 路径 ──────────────────────────────────────────────────────────────
    data_dir: Path = Path("data")
    db_path: Path = Path("data/voicekb.db")
    markdown_dir: Path = Path("data/transcripts")
    upload_dir: Path = Path("data/uploads")
    speaker_db_path: Path = Path("data/speakers.db")
    chroma_dir: Path = Path("data/chroma")

    # ── ASR ────────────────────────────────────────────────────────────────
    whisper_model: str = "small"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"

    # ── 声纹 ──────────────────────────────────────────────────────────────
    speaker_similarity_threshold: float = 0.85
    max_speakers_per_recording: int = 10

    # ── LLM ────────────────────────────────────────────────────────────────
    llm_backend: str = "openai_compatible"  # "openai_compatible" | "none"
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "Qwen/Qwen3-8B"
    llm_api_key: str = "not-needed"

    # ── 搜索 ──────────────────────────────────────────────────────────────
    embedding_model: str = "BAAI/bge-base-zh-v1.5"

    # ── 服务 ──────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8080

    def ensure_dirs(self) -> None:
        """创建所有必要的目录。"""
        for d in [
            self.data_dir,
            self.markdown_dir,
            self.upload_dir,
            self.chroma_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# 单例
settings = Settings()
