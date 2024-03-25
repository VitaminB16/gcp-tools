import pytest
import datetime
import pandas as pd
import pyarrow as pa
from google.cloud import bigquery

from gcp_tools.schema import enforce_schema, infer_schema, Schema


@pytest.mark.parametrize(
    "data",
    [
        {
            "a": [1, 2, 3],
            "b": ["a", "b", "c"],
            "c": [1, 2, 3],
        },
        pd.DataFrame(
            {
                "a": [1, 2, 3],
                "b": ["a", "b", "c"],
                "c": [1, 2, 3],
            }
        ),
    ],
)
def test_enforce_schema(data):
    schema = {
        "a": float,
        "b": lambda x: x.upper(),
        "c": {1: "one", 2: "two", 3: "three"},
    }
    d = enforce_schema(data, schema)
    output = d
    if isinstance(data, pd.DataFrame):
        output = d.to_dict(orient="list")
    assert output["a"] == [1.0, 2.0, 3.0]
    assert output["b"] == ["A", "B", "C"]
    assert output["c"] == ["one", "two", "three"]


def test_infer_schema():
    success = {}
    data = {
        "a": [1, 2, 3],
        "b": ["a", "b", "c"],
        "c": [1.0, 2.0, 3.0],
        "date": [datetime.datetime.now() for _ in range(3)],
    }
    python_schema = infer_schema(data)
    success[0] = python_schema == {
        "a": int,
        "b": str,
        "c": float,
        "date": datetime.datetime,
    }
    data = {"a": 1, "b": [2.0], "c": {"c1": ["w", "w"], "c2": [0, 1]}}
    python_schema = infer_schema(data)
    success[1] = python_schema == {
        "a": int,
        "b": float,
        "c": {"c1": str, "c2": int},
    }
    data = pd.DataFrame(
        {
            "a": [1, 2, 3],
            "b": ["a", "b", "c"],
            "c": [1.0, 2.0, 3.0],
            "date": [datetime.datetime.now() for _ in range(3)],
        }
    )
    pandas_schema = infer_schema(data)
    success[2] = pandas_schema == {
        "a": int,
        "b": str,
        "c": float,
        "date": "datetime64[ns]",
    }
    failed = [k for k, v in success.items() if not v]
    assert not failed


def test_schema():
    data = {
        "a": [1, 2, 3],
        "b": ["a", "b", "c"],
        "c": [1.0, 2.0, 3.0],
        "date": [datetime.datetime.now() for _ in range(3)],
    }
    inferred_schema = Schema(data).infer_schema()
    python_schema = inferred_schema.python()
    bigquery_schema = inferred_schema.bigquery()
    str_schema = inferred_schema.str()
    pyarrow_schema = inferred_schema.pyarrow()
    assert inferred_schema.schema == {
        "a": int,
        "b": str,
        "c": float,
        "date": datetime.datetime,
    }
    assert python_schema == {
        "a": int,
        "b": str,
        "c": float,
        "date": datetime.datetime,
    }
    assert bigquery_schema == [
        bigquery.SchemaField("a", "INTEGER"),
        bigquery.SchemaField("b", "STRING"),
        bigquery.SchemaField("c", "FLOAT"),
        bigquery.SchemaField("date", "DATETIME"),
    ]
    assert str_schema == {
        "a": "int",
        "b": "str",
        "c": "float",
        "date": "datetime",
    }
    assert pyarrow_schema == pa.schema(
        [
            pa.field("a", pa.int64()),
            pa.field("b", pa.string()),
            pa.field("c", pa.float64()),
            pa.field("date", pa.timestamp("ns")),
        ]
    )


def test_schema_nested():
    data = {
        "a": [1, 2, 3],
        "b": ["a", "b", "c"],
        "c": [1.0, 2.0, 3.0],
        "date": [datetime.datetime.now() for _ in range(3)],
        "nested": {"a": [1, 2, 3], "b": ["a", "b", "c"]},
    }
    inferred_schema = Schema(data).infer_schema()
    python_schema = inferred_schema.python()
    bigquery_schema = inferred_schema.bigquery()
    str_schema = inferred_schema.str()
    pyarrow_schema = inferred_schema.pyarrow()
    assert inferred_schema.schema == {
        "a": int,
        "b": str,
        "c": float,
        "date": datetime.datetime,
        "nested": {"a": int, "b": str},
    }
    assert python_schema == {
        "a": int,
        "b": str,
        "c": float,
        "date": datetime.datetime,
        "nested": {"a": int, "b": str},
    }
    assert bigquery_schema == [
        bigquery.SchemaField("a", "INTEGER"),
        bigquery.SchemaField("b", "STRING"),
        bigquery.SchemaField("c", "FLOAT"),
        bigquery.SchemaField("date", "DATETIME"),
        bigquery.SchemaField(
            "nested",
            "RECORD",
            mode="NULLABLE",
            fields=[
                bigquery.SchemaField("a", "INTEGER"),
                bigquery.SchemaField("b", "STRING"),
            ],
        ),
    ]
    assert str_schema == {
        "a": "int",
        "b": "str",
        "c": "float",
        "date": "datetime",
        "nested": {"a": "int", "b": "str"},
    }
    assert pyarrow_schema == pa.schema(
        [
            pa.field("a", pa.int64()),
            pa.field("b", pa.string()),
            pa.field("c", pa.float64()),
            pa.field("date", pa.timestamp("ns")),
            pa.field(
                "nested",
                pa.struct(
                    [
                        pa.field("a", pa.int64()),
                        pa.field("b", pa.string()),
                    ]
                ),
            ),
        ]
    )
