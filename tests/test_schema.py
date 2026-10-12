from pathlib import Path


def test_sql_schema_has_expected_tables_and_constraints():
    schema = (Path(__file__).parents[1] / "database" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE dbo.Devices" in schema
    assert "CREATE TABLE dbo.Measurements" in schema
    assert "CK_Measurements_Humidity" in schema
