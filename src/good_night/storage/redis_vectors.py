"""Redis vector storage for resolution similarity search.

Stores resolution embeddings in Redis for semantic search.
Used to find similar past resolutions when generating new ones.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import redis
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def _get_redis_config() -> dict:
    """Get Redis config from environment variables."""
    return {
        "host": os.environ.get("REDIS_HOST", "localhost"),
        "port": int(os.environ.get("REDIS_PORT", "6379")),
        "decode_responses": True,
        "username": os.environ.get("REDIS_USERNAME", "default"),
        "password": os.environ.get("REDIS_PASSWORD", ""),
    }

INDEX_NAME = "idx:resolutions_vss"
KEY_PREFIX = "resolution:"
VECTOR_DIMENSION = 384  # all-MiniLM-L6-v2 dimension


class RedisVectorStore:
    """Vector store for resolutions using Redis."""

    def __init__(self):
        self._client = None
        self._embedder = None
        self._index_created = False

    @property
    def client(self):
        """Lazy Redis client initialization."""
        if self._client is None:
            try:
                import redis
                self._client = redis.Redis(**_get_redis_config())
                self._client.ping()
                logger.info("Connected to Redis")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                raise
        return self._client

    @property
    def embedder(self):
        """Lazy embedder initialization."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Loaded sentence transformer model")
            except Exception as e:
                logger.warning(f"Failed to load sentence transformer: {e}")
                raise
        return self._embedder

    def ensure_index(self) -> bool:
        """Create the vector index if it doesn't exist."""
        if self._index_created:
            return True

        try:
            from redis.commands.search.field import (
                NumericField,
                TagField,
                TextField,
                VectorField,
            )
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType

            # Check if index exists
            try:
                self.client.ft(INDEX_NAME).info()
                self._index_created = True
                logger.info(f"Index {INDEX_NAME} already exists")
                return True
            except Exception:
                pass  # Index doesn't exist, create it

            schema = (
                TextField("$.title", as_name="title"),
                TextField("$.description", as_name="description"),
                TextField("$.rationale", as_name="rationale"),
                TextField("$.resolution_id", no_stem=True, as_name="resolution_id"),
                TextField("$.target", no_stem=True, as_name="target"),
                TextField("$.operation", no_stem=True, as_name="operation"),
                TextField("$.created_at", no_stem=True, as_name="created_at"),
                TagField("$.type", as_name="type"),
                TagField("$.connector_id", as_name="connector_id"),
                TagField("$.local_change", as_name="local_change"),
                NumericField("$.created_at_ts", as_name="created_at_ts"),
                VectorField(
                    "$.embedding",
                    "FLAT",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": VECTOR_DIMENSION,
                        "DISTANCE_METRIC": "COSINE",
                    },
                    as_name="vector",
                ),
            )

            definition = IndexDefinition(
                prefix=[KEY_PREFIX],
                index_type=IndexType.JSON
            )

            self.client.ft(INDEX_NAME).create_index(
                fields=schema,
                definition=definition
            )
            self._index_created = True
            logger.info(f"Created index {INDEX_NAME}")
            return True

        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False

    def _create_resolution_text(self, action: dict[str, Any]) -> str:
        """Create searchable text from a resolution action."""
        parts = []

        # Add type
        if action.get("type"):
            parts.append(f"Type: {action['type']}")

        # Add target
        if action.get("target"):
            parts.append(f"Target: {action['target']}")

        # Add content fields
        content = action.get("content", {})
        if content.get("title"):
            parts.append(f"Title: {content['title']}")
        if content.get("description"):
            parts.append(f"Description: {content['description']}")

        # Add rationale
        if action.get("rationale"):
            parts.append(f"Rationale: {action['rationale']}")

        # Add issue refs
        if action.get("issue_refs"):
            parts.append(f"Issues: {', '.join(action['issue_refs'])}")

        return "\n".join(parts)

    def store_resolution(
        self,
        resolution_id: str,
        connector_id: str,
        action: dict[str, Any],
        created_at: datetime | None = None,
    ) -> bool:
        """Store a resolution action as a vector in Redis.

        Args:
            resolution_id: Unique ID for the resolution
            connector_id: ID of the connector that generated this
            action: The resolution action dict
            created_at: When the resolution was created

        Returns:
            True if stored successfully
        """
        try:
            self.ensure_index()

            # Create text for embedding
            text = self._create_resolution_text(action)
            if not text.strip():
                logger.warning(f"Empty text for resolution {resolution_id}, skipping")
                return False

            # Generate embedding
            embedding = self.embedder.encode(text).astype(np.float32).tolist()

            # Prepare document
            created_at = created_at or datetime.now(timezone.utc)
            content = action.get("content", {})

            doc = {
                "resolution_id": resolution_id,
                "connector_id": connector_id,
                "type": action.get("type", "unknown"),
                "target": action.get("target", ""),
                "title": content.get("title", ""),
                "description": content.get("description", ""),
                "rationale": action.get("rationale", ""),
                "issue_refs": action.get("issue_refs", []),
                "local_change": action.get("local_change", False),
                "operation": action.get("operation", "create"),
                "created_at": created_at.isoformat(),
                "created_at_ts": created_at.timestamp(),
                "embedding": embedding,
            }

            # Generate unique key for this action
            action_id = f"{resolution_id}:{action.get('target', 'unknown')}"
            key = f"{KEY_PREFIX}{action_id}"

            # Store in Redis
            self.client.json().set(key, "$", doc)
            logger.info(f"Stored resolution action: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to store resolution: {e}")
            return False

    def search_similar(
        self,
        query_text: str,
        k: int = 5,
        min_age_days: int = 7,
        connector_id: str | None = None,
        min_score: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Search for similar resolutions.

        Args:
            query_text: Text to search for (issue description, etc.)
            k: Number of results to return
            min_age_days: Only return resolutions older than this many days
            connector_id: Optional filter by connector
            min_score: Minimum similarity score (0-1, higher is more similar)

        Returns:
            List of similar resolution documents with scores
        """
        try:
            self.ensure_index()

            from redis.commands.search.query import Query

            # Generate query embedding
            query_embedding = self.embedder.encode(query_text).astype(np.float32)

            # Calculate cutoff timestamp
            cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
            cutoff_ts = cutoff.timestamp()

            # Build filter
            filter_parts = [f"@created_at_ts:[-inf {cutoff_ts}]"]
            if connector_id:
                filter_parts.append(f"@connector_id:{{{connector_id}}}")

            filter_str = " ".join(filter_parts)

            # Build KNN query with filter
            # Don't use return_fields to get full JSON document
            query = (
                Query(f"({filter_str})=>[KNN {k} @vector $query_vector AS vector_score]")
                .sort_by("vector_score")
                .dialect(2)
            )

            # Execute search
            results = self.client.ft(INDEX_NAME).search(
                query,
                {"query_vector": query_embedding.tobytes()}
            )

            # Process results
            similar = []
            for doc in results.docs:
                # Convert cosine distance to similarity score (1 - distance)
                vector_score = float(getattr(doc, "vector_score", 1.0))
                score = 1 - vector_score
                if score < min_score:
                    continue

                # Parse the JSON document data
                doc_data = {}
                json_str = getattr(doc, "json", None)
                if json_str:
                    try:
                        doc_data = json.loads(json_str)
                    except (json.JSONDecodeError, TypeError):
                        pass

                similar.append({
                    "score": round(score, 3),
                    "resolution_id": doc_data.get("resolution_id", ""),
                    "connector_id": doc_data.get("connector_id", ""),
                    "type": doc_data.get("type", ""),
                    "target": doc_data.get("target", ""),
                    "title": doc_data.get("title", ""),
                    "description": doc_data.get("description", ""),
                    "rationale": doc_data.get("rationale", ""),
                    "issue_refs": doc_data.get("issue_refs", []),
                    "local_change": doc_data.get("local_change", False),
                    "operation": doc_data.get("operation", ""),
                    "created_at": doc_data.get("created_at", ""),
                })

            logger.info(f"Found {len(similar)} similar resolutions for query")
            return similar

        except Exception as e:
            logger.error(f"Failed to search similar resolutions: {e}")
            return []

    def search_by_issue(
        self,
        issue: dict[str, Any],
        k: int = 5,
        min_age_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Search for resolutions similar to an issue.

        Args:
            issue: Issue dict with title, description, type fields
            k: Number of results to return
            min_age_days: Only return resolutions older than this

        Returns:
            List of similar resolution documents with scores
        """
        # Build query text from issue
        parts = []
        if issue.get("type"):
            parts.append(f"Type: {issue['type']}")
        if issue.get("title"):
            parts.append(f"Title: {issue['title']}")
        if issue.get("description"):
            parts.append(f"Description: {issue['description']}")

        query_text = "\n".join(parts)
        if not query_text.strip():
            return []

        return self.search_similar(
            query_text=query_text,
            k=k,
            min_age_days=min_age_days,
        )

    def delete_resolution(self, resolution_id: str) -> int:
        """Delete all actions for a resolution.

        Args:
            resolution_id: The resolution ID to delete

        Returns:
            Number of keys deleted
        """
        try:
            pattern = f"{KEY_PREFIX}{resolution_id}:*"
            keys = list(self.client.scan_iter(pattern))
            if keys:
                result = self.client.delete(*keys)
                return int(result) if result else 0
            return 0
        except Exception as e:
            logger.error(f"Failed to delete resolution: {e}")
            return 0

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the vector store."""
        try:
            info = self.client.ft(INDEX_NAME).info()
            return {
                "num_docs": info.get("num_docs", 0),
                "indexing_failures": info.get("hash_indexing_failures", 0),
                "index_name": INDEX_NAME,
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}


# Singleton instance
_store: RedisVectorStore | None = None


def get_vector_store() -> RedisVectorStore:
    """Get the singleton vector store instance."""
    global _store
    if _store is None:
        _store = RedisVectorStore()
    return _store
