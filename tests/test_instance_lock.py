import pytest
from fastapi.testclient import TestClient
from tenderproof.main import create_app


def test_second_server_cannot_recover_active_first_server(tmp_path):
    with TestClient(create_app(tmp_path)) as first:
        assert first.get('/api/health').status_code == 200
        with pytest.raises(RuntimeError, match="already using this data directory"):
            with TestClient(create_app(tmp_path)):
                raise AssertionError("A second instance must not start against the same data")
        assert first.get('/api/health').status_code == 200
    with TestClient(create_app(tmp_path)) as restarted:
        assert restarted.get('/api/health').status_code == 200
