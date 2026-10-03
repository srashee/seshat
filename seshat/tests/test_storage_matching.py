import numpy as np
import pytest
from app.database import Database
from app.recognition import MODEL_ID, match


def test_persistence_model_isolation(runtime, face):
    runtime.db.add("Saad", face.embedding, MODEL_ID, "first", 10)
    reopened = Database(runtime.db.path)
    assert reopened.people()[0]["samples"] == 1
    assert np.array_equal(reopened.embeddings(MODEL_ID)[0][1], face.embedding)
    assert reopened.embeddings("different-model") == []


def test_threshold_and_person_aggregation(runtime):
    vector = np.array([1, 0], dtype=np.float32)
    samples = [("Saad", np.array([0, 1])), ("Saad", np.array([0.6, 0.8]))]
    runtime.settings.recognition_threshold = 0.6
    assert match(vector, samples, runtime.settings)["person"] == "Saad"
    runtime.settings.recognition_threshold = 0.61
    assert match(vector, samples, runtime.settings)["person"] == "Unknown"
    assert match(vector, [], runtime.settings)["distance"] is None


def test_ambiguous_identity(runtime, face):
    result = match(face.embedding, [("Saad", face.embedding), ("Other", face.embedding)], runtime.settings)
    assert result["person"] == "Unknown" and result["margin"] == 0


def test_database_future_schema_rejected(runtime):
    with runtime.db.connect() as db:
        db.execute("PRAGMA user_version=20")
    with pytest.raises(RuntimeError, match="schema"):
        Database(runtime.db.path)
