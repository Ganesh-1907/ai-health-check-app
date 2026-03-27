from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class HeartKnowledgeBase:
    def __init__(self) -> None:
        data_path = Path(__file__).resolve().parent.parent / "data" / "heart_knowledge.json"
        self.documents: list[dict[str, Any]] = json.loads(data_path.read_text(encoding="utf-8"))
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform([doc["text"] for doc in self.documents])

    def retrieve(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        clean_query = (query or "").strip()
        if not clean_query:
            return []

        query_vector = self.vectorizer.transform([clean_query])
        scores = cosine_similarity(query_vector, self.matrix).flatten()
        ranked_indices = scores.argsort()[::-1]

        results: list[dict[str, Any]] = []
        for index in ranked_indices:
            score = float(scores[index])
            if score <= 0:
                continue
            results.append({**self.documents[int(index)], "score": round(score, 3)})
            if len(results) >= top_k:
                break
        return results


@lru_cache
def get_heart_knowledge_base() -> HeartKnowledgeBase:
    return HeartKnowledgeBase()
