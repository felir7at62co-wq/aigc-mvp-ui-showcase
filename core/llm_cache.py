"""
AIGC Pipeline — LLM 响应缓存

实现对相同 prompt 的 LLM 调用缓存到本地 SQLite，避免重复消耗 token。

参考了 claw-code-main/rust/crates/api/src/prompt_cache.rs 的设计理念，但使用 Python 语言实现。
"""
import os
import sys
import sqlite3
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 缓存配置
DEFAULT_COMPLETION_TTL = timedelta(minutes=5)  # 完成响应的 TTL
DEFAULT_PROMPT_TTL = timedelta(minutes=30)    # 提示的 TTL
DEFAULT_CACHE_BREAK_MIN_DROP = 2000           # 最小的 token 下降量
REQUEST_FINGERPRINT_VERSION = 1               # 指纹版本
REQUEST_FINGERPRINT_PREFIX = "v1"
DEFAULT_CACHE_PATH = "data/llm_cache.db"


def _get_default_cache_path() -> str:
    """返回持久化的缓存路径（exe 旁），避免在临时目录或 CWD 下创建。"""
    if getattr(sys, "frozen", False):
        from core.paths import get_data_dir
        return os.path.join(get_data_dir(), "data", "llm_cache.db")
    return DEFAULT_CACHE_PATH

@dataclass
class CacheEntry:
    """缓存条目数据类"""
    prompt_hash: str
    response: str
    model: str
    cached_at: datetime
    fingerprint_version: int = REQUEST_FINGERPRINT_VERSION


class LLMCache:
    """LLM 响应缓存类"""

    def __init__(self, cache_path: str = ""):
        """初始化缓存

        Args:
            cache_path: SQLite 数据库路径（空字符串使用默认路径）
        """
        self.cache_path = cache_path or _get_default_cache_path()
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        # 确保数据库文件所在的目录存在
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        # 创建缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_hash TEXT NOT NULL UNIQUE,
                response TEXT NOT NULL,
                model TEXT NOT NULL,
                cached_at INTEGER NOT NULL,
                fingerprint_version INTEGER NOT NULL,
                hits INTEGER DEFAULT 0
            )
        """)

        # 创建统计信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_stats (
                id INTEGER PRIMARY KEY,
                tracked_requests INTEGER DEFAULT 0,
                completion_cache_hits INTEGER DEFAULT 0,
                completion_cache_misses INTEGER DEFAULT 0,
                completion_cache_writes INTEGER DEFAULT 0
            )
        """)

        # 确保统计信息表有一条记录
        cursor.execute("SELECT COUNT(*) FROM cache_stats")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO cache_stats (id) VALUES (1)")

        conn.commit()
        conn.close()

    def _compute_prompt_hash(self, prompt: str, model: str) -> str:
        """计算提示的哈希键"""
        content = f"{REQUEST_FINGERPRINT_PREFIX}-{REQUEST_FINGERPRINT_VERSION}-{model}-{prompt}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def get(self, prompt: str, model: str) -> Optional[str]:
        """从缓存中查找响应

        Args:
            prompt: 提示文本
            model: 模型名称

        Returns:
            缓存的响应文本或 None
        """
        prompt_hash = self._compute_prompt_hash(prompt, model)

        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        # 查找缓存条目
        cursor.execute("""
            SELECT response, cached_at, fingerprint_version, hits
            FROM llm_cache
            WHERE prompt_hash = ?
        """, (prompt_hash,))

        row = cursor.fetchone()

        if row:
            response, cached_at, fingerprint_version, hits = row

            # 检查指纹版本
            if fingerprint_version != REQUEST_FINGERPRINT_VERSION:
                logger.debug("缓存版本不匹配，删除旧条目")
                cursor.execute("DELETE FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,))
                conn.commit()
                conn.close()
                self._update_stats(completion_cache_misses=1)
                return None

            # 检查过期时间
            cached_datetime = datetime.fromtimestamp(cached_at)
            if datetime.now() - cached_datetime > DEFAULT_COMPLETION_TTL:
                logger.debug("缓存已过期，删除条目")
                cursor.execute("DELETE FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,))
                conn.commit()
                conn.close()
                self._update_stats(completion_cache_misses=1)
                return None

            # 更新命中次数
            cursor.execute("UPDATE llm_cache SET hits = ? WHERE prompt_hash = ?",
                         (hits + 1, prompt_hash))
            conn.commit()
            conn.close()

            logger.debug(f"缓存命中: {prompt_hash[:8]}")
            self._update_stats(completion_cache_hits=1)

            return response

        conn.close()
        self._update_stats(completion_cache_misses=1)
        logger.debug(f"缓存未命中: {prompt_hash[:8]}")

        return None

    def set(self, prompt: str, response: str, model: str):
        """将响应存储到缓存

        Args:
            prompt: 提示文本
            response: 响应文本
            model: 模型名称
        """
        prompt_hash = self._compute_prompt_hash(prompt, model)
        cached_at = int(datetime.now().timestamp())

        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        # 检查是否已存在条目
        cursor.execute("SELECT id FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,))
        existing_id = cursor.fetchone()

        if existing_id:
            # 更新现有条目
            cursor.execute("""
                UPDATE llm_cache
                SET response = ?, model = ?, cached_at = ?, hits = 0
                WHERE prompt_hash = ?
            """, (response, model, cached_at, prompt_hash))
        else:
            # 插入新条目
            cursor.execute("""
                INSERT INTO llm_cache
                (prompt_hash, response, model, cached_at, fingerprint_version, hits)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (prompt_hash, response, model, cached_at, REQUEST_FINGERPRINT_VERSION))

        conn.commit()
        conn.close()

        self._update_stats(completion_cache_writes=1)
        logger.debug(f"响应已缓存: {prompt_hash[:8]}")

    def cleanup(self) -> int:
        """清理过期的缓存条目

        Returns:
            删除的过期条目数
        """
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        # 删除过期的条目
        expiry_time = int((datetime.now() - DEFAULT_COMPLETION_TTL).timestamp())
        cursor.execute("DELETE FROM llm_cache WHERE cached_at < ?", (expiry_time,))
        deleted = cursor.rowcount

        conn.commit()
        conn.close()

        if deleted > 0:
            logger.debug(f"清理了 {deleted} 个过期缓存条目")

        return deleted

    def delete(self, prompt: str, model: str):
        """从缓存中删除指定条目"""
        prompt_hash = self._compute_prompt_hash(prompt, model)
        try:
            conn = sqlite3.connect(self.cache_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM llm_cache WHERE prompt_hash = ?", (prompt_hash,))
            conn.commit()
            conn.close()
            logger.debug(f"缓存已清除: {prompt_hash[:8]}")
        except Exception as e:
            logger.warning(f"清除缓存失败: {e}")

    def _update_stats(self, **kwargs):
        """更新统计信息"""
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        # 构建更新语句
        updates = []
        params = []

        if "tracked_requests" in kwargs:
            updates.append("tracked_requests = tracked_requests + ?")
            params.append(kwargs["tracked_requests"])

        if "completion_cache_hits" in kwargs:
            updates.append("completion_cache_hits = completion_cache_hits + ?")
            params.append(kwargs["completion_cache_hits"])

        if "completion_cache_misses" in kwargs:
            updates.append("completion_cache_misses = completion_cache_misses + ?")
            params.append(kwargs["completion_cache_misses"])

        if "completion_cache_writes" in kwargs:
            updates.append("completion_cache_writes = completion_cache_writes + ?")
            params.append(kwargs["completion_cache_writes"])

        if updates:
            cursor.execute(f"UPDATE cache_stats SET {', '.join(updates)} WHERE id = 1", params)

        conn.commit()
        conn.close()

    def get_stats(self) -> Dict[str, int]:
        """获取缓存统计信息

        Returns:
            统计信息字典
        """
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM cache_stats")
        row = cursor.fetchone()

        conn.close()

        if row:
            _, tracked_requests, hits, misses, writes = row
            return {
                "tracked_requests": tracked_requests,
                "completion_cache_hits": hits,
                "completion_cache_misses": misses,
                "completion_cache_writes": writes,
                "hit_rate": hits / (hits + misses) if (hits + misses) > 0 else 0
            }

        return {
            "tracked_requests": 0,
            "completion_cache_hits": 0,
            "completion_cache_misses": 0,
            "completion_cache_writes": 0,
            "hit_rate": 0
        }

    def clear_cache(self) -> int:
        """清除所有缓存

        Returns:
            清除的条目数
        """
        conn = sqlite3.connect(self.cache_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM llm_cache")
        count = cursor.fetchone()[0]

        cursor.execute("DELETE FROM llm_cache")
        cursor.execute("""
            UPDATE cache_stats
            SET tracked_requests = 0, completion_cache_hits = 0,
                completion_cache_misses = 0, completion_cache_writes = 0
        """)

        conn.commit()
        conn.close()

        logger.info(f"已清除所有缓存，共 {count} 个条目")

        return count


class CacheManager:
    """缓存管理器"""

    _instance: Optional[LLMCache] = None

    @classmethod
    def get_cache(cls, cache_path: str = DEFAULT_CACHE_PATH) -> LLMCache:
        """获取缓存实例（单例模式）

        Args:
            cache_path: SQLite 数据库路径

        Returns:
            LLMCache 实例
        """
        if cls._instance is None:
            cls._instance = LLMCache(cache_path)

        return cls._instance


# 便捷函数
def get_cache() -> LLMCache:
    """获取默认的缓存实例"""
    return CacheManager.get_cache()


def cache_response(prompt: str, response: str, model: str) -> None:
    """存储响应到缓存的便捷函数"""
    get_cache().set(prompt, response, model)


def get_cached_response(prompt: str, model: str) -> Optional[str]:
    """从缓存获取响应的便捷函数"""
    return get_cache().get(prompt, model)


def get_cache_stats() -> Dict[str, int]:
    """获取缓存统计信息的便捷函数"""
    return get_cache().get_stats()


def cleanup_cache() -> int:
    """清理过期缓存的便捷函数"""
    return get_cache().cleanup()


def clear_cache() -> int:
    """清除所有缓存的便捷函数"""
    return get_cache().clear_cache()


# 使用示例
if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

    # 测试缓存功能
    cache = LLMCache()

    # 测试设置和获取响应
    prompt = "你好，世界！"
    model = "ark-code-latest"
    response = "你好！我是 AI 助手，很高兴为你服务。"

    cache.set(prompt, response, model)
    print("设置响应到缓存")

    cached_response = cache.get(prompt, model)
    print(f"从缓存获取响应: {cached_response}")

    # 测试不同模型
    response2 = cache.get(prompt, "other-model")
    print(f"获取不同模型的响应: {response2}")

    # 测试统计信息
    print("\n缓存统计信息:")
    stats = cache.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # 测试清理
    print(f"\n清理过期缓存: 删除了 {cache.cleanup()} 个条目")

    print("\n测试完成！")