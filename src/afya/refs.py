"""`module:attr` references, resolved.

A register that claims software enforcement has to name software, and the claim is only worth
anything if something walks the reference and says whether it lands. §23's risk register and §24.6's
mitigations were the first two tables to need that, and §17.1's six instruments and §17.2's seven
principles are the third and fourth — so the walk lives here rather than being copied into each.

A `None` reference resolves: it is how a table says "this one is a human process", and answering
False for it would put every process control in the unbacked list, which is the opposite of what
the list is for.
"""
import importlib


def resolves(ref: str | None) -> bool:
	"""Whether a `module:attr` reference names something that exists.

	The attribute path may be dotted (`Module.Class.method`) and every step is walked, so a reference
	to a method that was renamed off a class fails here rather than at the call site that no longer
	exists. A reference with no `:` is not a reference — the module alone names a package, not the
	thing enforcing the control.
	"""
	if ref is None:
		return True
	module_name, _, attr_path = ref.partition(':')
	if not attr_path:
		return False
	try:
		target: object = importlib.import_module(module_name)
	except ImportError:
		return False
	for part in attr_path.split('.'):
		if not hasattr(target, part):
			return False
		target = getattr(target, part)
	return True
