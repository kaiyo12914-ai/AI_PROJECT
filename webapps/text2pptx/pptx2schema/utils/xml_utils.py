from __future__ import annotations

import xml.etree.ElementTree as ET


def parse_xml_bytes(raw: bytes) -> ET.Element:
    return ET.fromstring(raw)
