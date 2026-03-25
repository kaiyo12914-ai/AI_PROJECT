from __future__ import annotations

import io
from pathlib import Path
from typing import Union

from pptx import Presentation


InputLike = Union[str, Path, bytes, bytearray]


def load_presentation(input_data: InputLike) -> Presentation:
    if isinstance(input_data, (bytes, bytearray)):
        return Presentation(io.BytesIO(bytes(input_data)))
    return Presentation(str(input_data))
