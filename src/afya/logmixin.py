"""Logging mixin — `_log_` prefixed methods per project convention."""
import logging


class LogMixin:
	_logger: logging.Logger | None = None

	def _log(self) -> logging.Logger:
		if self._logger is None:
			self._logger = logging.getLogger(type(self).__module__ + '.' + type(self).__name__)
		return self._logger

	def _log_info(self, msg: str, /, **fields: object) -> None:
		self._log().info('%s %s', msg, fields or '')

	def _log_warn(self, msg: str, /, **fields: object) -> None:
		self._log().warning('%s %s', msg, fields or '')

	def _log_error(self, msg: str, /, **fields: object) -> None:
		self._log().error('%s %s', msg, fields or '')