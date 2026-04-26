import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.fax_scanner_emr import HL7Listener


def test_hl7_listener_oru_processing():
    listener = HL7Listener()
    raw_message = (
        "MSH|^~\\&|LAB|HOSP|RAKSH|RAKSH|20240115||ORU^R01|MSG001|P|2.5\r"
        "PID|||12345^^^MRN||Kumar^Ramesh||19850615|M\r"
        "OBX|1|NM|718-7^Hemoglobin||11.8|g/dL|11.5-16.0|N|||F|||20240115\r"
        "OBX|2|NM|2947-0^TSH||3.5|mIU/L|0.5-5.5|N|||F|||20240115\r"
    )

    result = listener.process_message(raw_message)

    assert result["status"] == "processed"
    assert result["message_type"] == "ORU"
    assert result["patient"]["id"] == "12345"
    assert result["observation_count"] == 2


def test_hl7_listener_adt_processing():
    listener = HL7Listener()
    raw_message = (
        "MSH|^~\\&|ADT|HOSP|RAKSH|RAKSH|20240115||ADT^A01|MSG002|P|2.5\r"
        "PID|||54321^^^MRN||Sharma^Priya||19900322|F\r"
        "PV1||I|Ward3|||Dr^Patel\r"
    )

    result = listener.process_message(raw_message)

    assert result["status"] == "processed"
    assert result["message_type"] == "ADT"
    assert result["patient"]["id"] == "54321"


def test_hl7_listener_unsupported_message():
    listener = HL7Listener()
    raw_message = "MSH|^~\\&|SYS|HOSP|RAKSH|RAKSH|20240115||SIU^S12|MSG003|P|2.5\r"

    result = listener.process_message(raw_message)
    assert result["status"] == "unsupported"


def test_hl7_ack_generation():
    listener = HL7Listener()
    raw_message = "MSH|^~\\&|LAB|HOSP|RAKSH|RAKSH|20240115||ORU^R01|MSG001|P|2.5\r"

    ack = listener.build_ack(raw_message, "AA")

    assert "MSA|AA|MSG001" in ack
    assert "ACK" in ack


def test_hl7_ack_error():
    listener = HL7Listener()
    raw_message = "MSH|^~\\&|LAB|HOSP|RAKSH|RAKSH|20240115||ORU^R01|MSG001|P|2.5\r"

    ack = listener.build_ack(raw_message, "AE")
    assert "MSA|AE|MSG001" in ack


def test_hl7_empty_message():
    listener = HL7Listener()
    result = listener.process_message("")
    assert result["status"] == "unsupported"
