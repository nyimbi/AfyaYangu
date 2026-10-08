"""Cycle tracking service — calendar-method prediction, irregularity flagging, adolescent privacy note."""
from statistics import median

from afya.logmixin import LogMixin
from afya.women.views import CycleLog, CyclePrediction

_MIN_LOGS = 3


class WomenService(LogMixin):
	def __init__(self) -> None:
		self._logs: dict[str, list[CycleLog]] = {}
		assert self._logs == {}

	async def log(self, entry: CycleLog) -> int:
		assert entry.subject_ref, 'subject required'
		if entry.pain_level >= 7:
			self._log_warn('high dysmenorrhoea reported')
		self._logs.setdefault(entry.subject_ref, []).append(entry)
		return len(self._logs[entry.subject_ref])

	def predict(self, subject_ref: str, ref_date: str) -> CyclePrediction:
		logs = self._logs.get(subject_ref, [])
		assert logs, 'insufficient data: needs >= 3 cycles'
		specs = sorted(log.start_iso for log in logs)
		spans = sorted(
			int(a[5:7]) * 30 + int(a[8:10]) - (int(b[5:7]) * 30 + int(b[8:10]))
			for a, b in zip(specs[1:], specs[:-1])
		)
		spans = [s for s in spans if 20 <= s <= 45]
		if len(spans) < _MIN_LOGS - 1:
			return CyclePrediction(next_period_iso=None, fertile_window_days=None, cycle_regularity='insufficient_data', advise='Log at least 3 periods for predictions.')
		md = round(median(spans))
		regularity = 'regular' if spans and (max(spans) - min(spans)) <= 4 else 'irregular'
		last = logs[-1].start_iso
		day_ = int(last[8:10]) + md
		next_period = f'{last[:5]}{day_:02d}' if day_ <= 28 else next_period_fallback(last, day_)
		out = CyclePrediction(
			next_period_iso=next_period,
			fertile_window_days=None,
			cycle_regularity=regularity,
			advise=(
				'Cycle irregular across logs — consider clinic review.'
				if regularity == 'irregular'
				else f'Next period expected ~{next_period}; fertile window approx days {md - 15}–{md - 11} of cycle. Log daily for better predictions.'
			),
		)
		assert out.advise, 'advise required'
		return out


def next_period_fallback(last: str, day_: int) -> str:
	import math
	year, month = int(last[:4]), int(last[5:7])
	add_months = math.ceil(day_ / 28) - 1
	n_month = month + add_months
	n_day = day_ - add_months * 28
	return f'{year + (n_month - 1) // 12}-{(n_month - 1) % 12 + 1:02d}-{max(1, n_day):02d}'