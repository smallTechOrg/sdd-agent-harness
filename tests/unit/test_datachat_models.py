"""DataChat metadata models — roundtrip Dataset → Conversation → Message."""
import json

from sqlalchemy.orm import Session

from db.models import Conversation, Dataset, Message


def test_dataset_conversation_message_roundtrip(_isolated_db):
    schema = {"columns": [{"name": "region", "dtype": "string"}], "row_count": 3}
    with Session(_isolated_db) as s:
        ds = Dataset(
            filename="sales.csv",
            stored_path="data/uploads/abc.csv",
            file_type="csv",
            schema_json=json.dumps(schema),
            row_count=3,
        )
        s.add(ds)
        s.commit()
        dataset_id = ds.id

        conv = Conversation(dataset_id=dataset_id)
        s.add(conv)
        s.commit()
        conv_id = conv.id

        user_msg = Message(conversation_id=conv_id, role="user", content="totals?")
        chart = {"type": "bar", "title": "t", "labels": ["a"], "series": []}
        asst_msg = Message(
            conversation_id=conv_id,
            role="assistant",
            content="here you go",
            chart_json=json.dumps(chart),
        )
        s.add_all([user_msg, asst_msg])
        s.commit()

    with Session(_isolated_db) as s:
        ds = s.get(Dataset, dataset_id)
        assert ds.filename == "sales.csv"
        assert ds.file_type == "csv"
        assert json.loads(ds.schema_json)["row_count"] == 3

        msgs = (
            s.query(Message)
            .filter_by(conversation_id=conv_id)
            .order_by(Message.created_at)
            .all()
        )
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[0].chart_json is None
        assert json.loads(msgs[1].chart_json)["type"] == "bar"
