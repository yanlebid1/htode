"""
Data structures for phone number extraction results.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ExtractionResult:
    """
    Container for extracted phone numbers and an optional Viber contact link.
    """

    phone_numbers: List[str]
    viber_link: Optional[str] = None
