"""UUID7 string helpers per project convention."""
from uuid6 import uuid7


def uuid7str() -> str:
	return str(uuid7())