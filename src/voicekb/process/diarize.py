"""声纹分离 — resemblyzer d-vector + 谱聚类。"""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav
from sklearn.cluster import SpectralClustering

logger = logging.getLogger(__name__)

# 静默 resemblyzer 依赖的 webrtcvad 弃用警告
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")


@dataclass
class SpeakerSegment:
    """一个带说话人标签的时间段。"""
    start: float
    end: float
    speaker_label: str  # "SPEAKER_00", "SPEAKER_01", ...
    embedding: np.ndarray


class Diarizer:
    """声纹分离引擎。"""

    def __init__(self) -> None:
        logger.info("加载声纹模型 (resemblyzer)...")
        self._encoder = VoiceEncoder()
        logger.info("声纹模型加载完成")

    def diarize(self, audio_path: Path,
                num_speakers: int | None = None,
                window_sec: float = 3.0,
                step_sec: float = 1.5) -> list[SpeakerSegment]:
        """对音频进行声纹分离。

        Args:
            audio_path: 音频文件路径
            num_speakers: 说话人数量（None=自动检测）
            window_sec: 滑动窗口大小（秒）
            step_sec: 滑动步长（秒）
        """
        wav = preprocess_wav(audio_path)
        sr = 16000  # resemblyzer 预处理后固定 16kHz

        # 长录音自动增大步长，控制嵌入总数在 2000 以内
        audio_duration = len(wav) / sr
        if audio_duration > 1800:  # > 30 分钟
            step_sec = max(step_sec, audio_duration / 1500)
            logger.info("长录音 (%.0f分钟)，步长调整为 %.1fs", audio_duration / 60, step_sec)

        window_samples = int(window_sec * sr)
        step_samples = int(step_sec * sr)

        # 提取窗口级别的说话人嵌入
        embeddings: list[np.ndarray] = []
        timestamps: list[tuple[float, float]] = []

        for start_sample in range(0, len(wav) - window_samples, step_samples):
            segment = wav[start_sample:start_sample + window_samples]
            energy = float(np.sqrt(np.mean(segment ** 2)))
            if energy < 0.01:
                continue  # 跳过静音段

            embed = self._encoder.embed_utterance(segment)
            embeddings.append(embed)
            start_t = start_sample / sr
            timestamps.append((start_t, start_t + window_sec))

        if len(embeddings) < 2:
            logger.warning("有效语音段不足，无法进行声纹分离")
            return [SpeakerSegment(
                start=0.0, end=len(wav) / sr,
                speaker_label="SPEAKER_00",
                embedding=embeddings[0] if embeddings else np.zeros(256),
            )]

        embed_matrix = np.array(embeddings)

        # 自动检测说话人数量（使用特征值间隙法）
        if num_speakers is None:
            num_speakers = self._estimate_num_speakers(embed_matrix)

        num_speakers = min(num_speakers, len(embeddings))
        logger.info("声纹分离: %d 个有效段, %d 个说话人", len(embeddings), num_speakers)

        # 谱聚类
        n_neighbors = min(7, len(embeddings) - 1)
        clustering = SpectralClustering(
            n_clusters=num_speakers,
            affinity="nearest_neighbors",
            n_neighbors=max(2, n_neighbors),
            random_state=42,
        )
        labels = clustering.fit_predict(embed_matrix)

        # 构建结果
        result: list[SpeakerSegment] = []
        for (start_t, end_t), label, embed in zip(timestamps, labels, embeddings):
            result.append(SpeakerSegment(
                start=start_t,
                end=end_t,
                speaker_label=f"SPEAKER_{label:02d}",
                embedding=embed,
            ))

        return result

    def extract_embedding(self, audio_path: Path,
                          start: float, end: float) -> np.ndarray:
        """从音频的指定时间范围提取说话人嵌入。"""
        wav = preprocess_wav(audio_path)
        sr = 16000
        start_sample = int(start * sr)
        end_sample = min(int(end * sr), len(wav))
        segment = wav[start_sample:end_sample]

        if len(segment) < sr:  # 不足1秒，填充
            segment = np.pad(segment, (0, sr - len(segment)))

        return self._encoder.embed_utterance(segment)

    def compute_centroid(self, segments: list[SpeakerSegment],
                         label: str) -> np.ndarray:
        """计算某个说话人标签的嵌入质心。"""
        embeds = [s.embedding for s in segments if s.speaker_label == label]
        if not embeds:
            return np.zeros(256)
        return np.mean(embeds, axis=0)

    @staticmethod
    def _estimate_num_speakers(embeddings: np.ndarray,
                                max_speakers: int = 8) -> int:
        """用特征值间隙法估算说话人数量。"""
        from sklearn.metrics.pairwise import cosine_similarity

        sim_matrix = cosine_similarity(embeddings)
        np.fill_diagonal(sim_matrix, 0)

        # 计算拉普拉斯矩阵的特征值
        degree = np.sum(sim_matrix, axis=1)
        laplacian = np.diag(degree) - sim_matrix
        eigenvalues = np.sort(np.real(np.linalg.eigvals(laplacian)))

        # 找最大特征值间隙
        max_k = min(max_speakers, len(eigenvalues) - 1)
        gaps = np.diff(eigenvalues[:max_k + 1])

        if len(gaps) == 0:
            return 2

        # 从第2个特征值开始找间隙（第1个总是0）
        best_k = int(np.argmax(gaps[1:]) + 2) if len(gaps) > 1 else 2
        return max(2, min(best_k, max_speakers))
