import logging
from dataclasses import asdict, dataclass, field
import enum
from typing import Dict, Tuple, Sequence, List, Optional

from fpr.serialize_util import extract_fields, get_in

log = logging.getLogger("fpr.models.nodejs")


SerializedNodeJSMetadata = Dict
