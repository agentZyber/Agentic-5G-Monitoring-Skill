import os
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from threading import Lock

try:
    import chromadb
    from chromadb.config import Settings

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class VectorStore:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        self._client = None
        self._collection = None
        self._lock = Lock()

        if CHROMA_AVAILABLE:
            self._init_chroma()

    def _init_chroma(self):
        self._client = chromadb.Client(
            Settings(
                persist_directory=self.persist_directory, anonymized_telemetry=False
            )
        )
        self._collection = self._client.get_or_create_collection(
            name="network_context",
            metadata={"description": "5G Network context events for RAG"},
        )

    @property
    def is_available(self) -> bool:
        return CHROMA_AVAILABLE and self._collection is not None

    def add_event(
        self, event: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        if not self.is_available:
            return ""

        with self._lock:
            event_id = f"event_{datetime.utcnow().timestamp()}_{hash(str(event))}"

            text_repr = self._event_to_text(event)

            if metadata is None:
                metadata = {
                    "timestamp": event.get("timestamp", datetime.utcnow().isoformat()),
                    "external_id": event.get("externalId", ""),
                    "event_type": event.get("type", "unknown"),
                    "cell_id": event.get("locationInfo", {}).get("cellId", "")
                    if isinstance(event.get("locationInfo"), dict)
                    else "",
                }

            self._collection.add(
                documents=[text_repr], ids=[event_id], metadatas=[metadata]
            )

            return event_id

    def _event_to_text(self, event: Dict[str, Any]) -> str:
        parts = []
        if event.get("externalId"):
            parts.append(f"UE: {event['externalId']}")
        if event.get("type"):
            parts.append(f"Event type: {event['type']}")
        if isinstance(event.get("locationInfo"), dict):
            loc = event["locationInfo"]
            if loc.get("cellId"):
                parts.append(f"Cell ID: {loc['cellId']}")
            if loc.get("age"):
                parts.append(f"Age: {loc['age']}")
            if loc.get("ueLocationTimestamp"):
                parts.append(f"Time: {loc['ueLocationTimestamp']}")
        if event.get("timestamp"):
            parts.append(f"Recorded: {event['timestamp']}")
        return " | ".join(parts) if parts else json.dumps(event)

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not self.is_available:
            return []

        with self._lock:
            results = self._collection.query(
                query_texts=[query], n_results=n_results, where=filter_metadata
            )

        formatted = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                formatted.append(
                    {
                        "id": results["ids"][0][i],
                        "content": doc,
                        "metadata": results["metadatas"][0][i]
                        if results.get("metadatas")
                        else {},
                        "distance": results["distances"][0][i]
                        if results.get("distances")
                        else None,
                    }
                )

        return formatted

    def get_by_external_id(
        self, external_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        return self.search(
            query=f"UE {external_id}",
            n_results=limit,
            filter_metadata={"external_id": external_id},
        )

    def delete_old_events(self, days: int = 7) -> int:
        if not self.is_available:
            return 0

        cutoff = datetime.utcnow().timestamp() - (days * 86400)
        deleted = 0

        with self._lock:
            all_data = self._collection.get()
            ids_to_delete = []

            for i, meta in enumerate(all_data.get("metadatas", [])):
                if meta and meta.get("timestamp"):
                    try:
                        event_time = datetime.fromisoformat(
                            meta["timestamp"].replace("Z", "+00:00")
                        )
                        if event_time.timestamp() < cutoff:
                            ids_to_delete.append(all_data["ids"][i])
                    except (ValueError, TypeError):
                        pass

            if ids_to_delete:
                self._collection.delete(ids=ids_to_delete)
                deleted = len(ids_to_delete)

        return deleted

    def get_stats(self) -> Dict[str, Any]:
        if not self.is_available:
            return {
                "available": False,
                "reason": "ChromaDB not installed or collection not initialized",
            }

        with self._lock:
            count = self._collection.count()
            return {
                "available": True,
                "total_events": count,
                "persist_directory": self.persist_directory,
            }


class ContextVectorStore:
    def __init__(self):
        self.vector_store = VectorStore()
        self.in_memory_store: List[Dict[str, Any]] = []
        self.max_in_memory = 1000
        self._lock = Lock()

    @property
    def rag_available(self) -> bool:
        return self.vector_store.is_available

    def add_event(self, event: Dict[str, Any]) -> str:
        with self._lock:
            event["timestamp"] = datetime.utcnow().isoformat()
            self.in_memory_store.append(event)
            if len(self.in_memory_store) > self.max_in_memory:
                self.in_memory_store.pop(0)

            if self.vector_store.is_available:
                return self.vector_store.add_event(event)

        return ""

    def search_similar(
        self, query: str, n_results: int = 5, external_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.vector_store.is_available:
            return {
                "mode": "in_memory_fallback",
                "results": self._in_memory_search(query, n_results, external_id),
            }

        filter_meta = {"external_id": external_id} if external_id else None
        vector_results = self.vector_store.search(query, n_results, filter_meta)

        return {
            "mode": "vector",
            "query": query,
            "results": vector_results,
            "stats": self.vector_store.get_stats(),
        }

    def _in_memory_search(
        self, query: str, n_results: int, external_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        scored = []

        for event in reversed(self.in_memory_store):
            if external_id and event.get("externalId") != external_id:
                continue

            text = json.dumps(event).lower()
            if query_lower in text:
                scored.append({"event": event, "relevance": 1.0})
            elif any(word in text for word in query_lower.split()):
                scored.append({"event": event, "relevance": 0.5})

        return [
            {"event": item["event"], "relevance": item["relevance"]}
            for item in scored[:n_results]
        ]

    def get_ue_mobility_pattern(self, external_id: str) -> Dict[str, Any]:
        events = [e for e in self.in_memory_store if e.get("externalId") == external_id]

        if not events:
            return {"external_id": external_id, "pattern": "no_data"}

        cell_visits: Dict[str, int] = {}
        transitions: List[Dict[str, str]] = []
        last_cell = None

        for event in events:
            cell_id = (
                event.get("locationInfo", {}).get("cellId")
                if isinstance(event.get("locationInfo"), dict)
                else None
            )
            if cell_id:
                cell_visits[cell_id] = cell_visits.get(cell_id, 0) + 1
                if last_cell and last_cell != cell_id:
                    transitions.append({"from": last_cell, "to": cell_id})
                last_cell = cell_id

        return {
            "external_id": external_id,
            "total_events": len(events),
            "unique_cells_visited": len(cell_visits),
            "cell_distribution": cell_visits,
            "transitions": transitions[-10:],
            "primary_cell": max(cell_visits, key=cell_visits.get)
            if cell_visits
            else None,
        }

    def get_context_summary(self) -> Dict[str, Any]:
        if not self.in_memory_store:
            return {"status": "no_context", "events": []}

        recent = self.in_memory_store[-10:]
        alerts = [e for e in self.in_memory_store if e.get("type") == "alert"]
        unique_ues = set(
            e.get("externalId") for e in self.in_memory_store if e.get("externalId")
        )

        return {
            "status": "available",
            "event_count": len(self.in_memory_store),
            "unique_ues": len(unique_ues),
            "alert_count": len(alerts),
            "latest_event": self.in_memory_store[-1] if self.in_memory_store else None,
            "recent_events": recent,
            "vector_store_available": self.vector_store.is_available,
            "vector_stats": self.vector_store.get_stats()
            if self.vector_store.is_available
            else None,
        }


context_vector_store = ContextVectorStore()
