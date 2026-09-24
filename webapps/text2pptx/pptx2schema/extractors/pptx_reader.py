from __future__ import annotations

import io
from pathlib import Path
from typing import Union

try:
    from pptx import Presentation
except ImportError:
    Presentation = None


InputLike = Union[str, Path, bytes, bytearray]


def load_presentation(input_data: InputLike) -> Any:
    if Presentation is None:
        raise RuntimeError("python-pptx is not installed in the current environment.")
    if isinstance(input_data, (bytes, bytearray)):
        return Presentation(io.BytesIO(bytes(input_data)))
    return Presentation(str(input_data))
