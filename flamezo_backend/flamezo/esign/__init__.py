"""
eSign adapter factory. `api/esign.py` never imports a concrete adapter
directly — always through get_adapter(provider_key) — so adding Leegality
or Digio later, or switching the active provider per Agreement Template,
touches this one function and a new adapter file, nothing else.
"""

from .base import EsignAdapter
from .leegality_adapter import LeegalityAdapter
from .signyu_adapter import SignYuAdapter

_ADAPTERS: dict[str, type[EsignAdapter]] = {
	"signyu": SignYuAdapter,
	"leegality": LeegalityAdapter,
}


def get_adapter(provider_key: str) -> EsignAdapter:
	if provider_key == "clickwrap":
		raise ValueError(
			"clickwrap is not a real eSign provider — it's handled entirely "
			"in api/esign.py::record_clickwrap_acceptance() without calling "
			"any adapter. Don't route it through get_adapter()."
		)
	adapter_cls = _ADAPTERS.get(provider_key)
	if not adapter_cls:
		raise ValueError(
			f"No eSign adapter registered for provider '{provider_key}'. "
			f"Known providers: {sorted(_ADAPTERS)}"
		)
	return adapter_cls()
