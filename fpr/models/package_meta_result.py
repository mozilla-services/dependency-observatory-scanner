from typing import Union, TypeVar


# https://beepb00p.xyz/mypy-error-handling.html#kiss
T = TypeVar("T")
Result = Union[T, Exception]
