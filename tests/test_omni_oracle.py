import json
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.omni_oracle import record_knowledge, recall_knowledge


def test_record_and_recall():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Record
        rec1 = record_knowledge(
            type="decision",
            content="Use SQLite for sandbox MVP",
            tags=["sandbox", "sqlite"],
            knowledge_dir=tmp_path
        )
        assert rec1["status"] == "ok"
        
        rec2 = record_knowledge(
            type="bug_pattern",
            content="Missing commit in service layer",
            tags=["tx", "bug"],
            knowledge_dir=tmp_path
        )
        assert rec2["status"] == "ok"
        
        # Recall by tag
        res_tag = recall_knowledge(tags=["sandbox"], knowledge_dir=tmp_path)
        assert res_tag["count"] == 1
        assert res_tag["results"][0]["content"] == "Use SQLite for sandbox MVP"
        
        # Recall by type
        res_type = recall_knowledge(type="bug_pattern", knowledge_dir=tmp_path)
        assert res_type["count"] == 1
        assert res_type["results"][0]["content"] == "Missing commit in service layer"
        
        # Recall by query
        res_query = recall_knowledge(query="sqlite", knowledge_dir=tmp_path)
        assert res_query["count"] == 1
        assert "SQLite" in res_query["results"][0]["content"]
        
        print("test_record_and_recall: PASSED")


if __name__ == "__main__":
    try:
        test_record_and_recall()
        print("\nAll Omni-Oracle tests passed.")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
