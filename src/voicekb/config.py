"""配置管理 — 通过 .env 和环境变量加载设置。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """VoiceKB 全局配置。"""

    model_config = SettingsConfigDict(env_prefix="VOICEKB_", env_file=".env")

    # ── 路径（默认 ~/.voicekb/，用户数据不在项目目录中）─────────────────
    data_dir: Path = Path.home() / ".voicekb"
    db_path: Path = Path.home() / ".voicekb" / "voicekb.db"
    markdown_dir: Path = Path.home() / ".voicekb" / "transcripts"
    upload_dir: Path = Path.home() / ".voicekb" / "uploads"
    speaker_db_path: Path = Path.home() / ".voicekb" / "speakers.db"
    chroma_dir: Path = Path.home() / ".voicekb" / "chroma"

    # ── ASR（OpenAI Whisper API 兼容，本地 faster-whisper-server 或云端）────
    asr_base_url: str = "http://localhost:8000/v1"  # 本地 faster-whisper-server
    asr_model: str = "medium"  # 本地用 medium/large-v3，云端用 whisper-1
    asr_api_key: str = "not-needed"
    asr_language: str = "zh"

    # ── 声纹 ──────────────────────────────────────────────────────────────
    speaker_similarity_threshold: float = 0.85
    max_speakers_per_recording: int = 10

    # ── LLM ────────────────────────────────────────────────────────────────
    llm_backend: str = "openai_compatible"  # "openai_compatible" | "none"
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "Qwen3.5-35B-A3B"
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
