import io
import json
import logging

from app.core.logging import JsonFormatter, bind_run_id


def _capture() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.json")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_log_line_is_json_with_run_id_when_bound() -> None:
    logger, stream = _capture()
    with bind_run_id("run-123"):
        logger.info("deciding", extra={"sku": "ATTA-5KG"})
    record = json.loads(stream.getvalue())
    assert record["msg"] == "deciding"
    assert record["level"] == "INFO"
    assert record["run_id"] == "run-123"
    assert record["sku"] == "ATTA-5KG"


def test_run_id_is_cleared_after_the_block() -> None:
    logger, stream = _capture()
    with bind_run_id("run-123"):
        pass
    logger.info("outside")
    assert json.loads(stream.getvalue())["run_id"] is None
