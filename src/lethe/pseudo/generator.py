from functools import lru_cache

from diskcache import Index


class PseudonymGenerator:
    """Assigns integers on the supplied patient ids and stores the mappings in a local db"""

    _lookup_ix: Index
    _pseudo_prefix: str

    _max_counter_name = "__max__"

    def __init__(self, directory: str, pseudonym_prefix: str):
        self._lookup_ix = Index(directory)
        self._pseudo_prefix = pseudonym_prefix

    def assign(self, patient_id: str) -> int:
        """Create a new pseudo id for the given patient_id if does not exist already"""
        pseudo_id = self._lookup_ix.get(patient_id)
        if pseudo_id is not None:
            return pseudo_id
        with self._lookup_ix.cache.transact():
            # Double check, now that we are inside a transaction.
            # Surely not needed if single-threaded (and single-process) but better be safe
            pseudo_id = self._lookup_ix.get(patient_id)
            if pseudo_id is not None:
                return pseudo_id

            pseudo_id = self._lookup_ix.cache.incr(self._max_counter_name)
            self._lookup_ix[patient_id] = pseudo_id

            return pseudo_id

    def _mk_pseudonym(self, pseudo_id: int) -> str:
        return f"{self._pseudo_prefix}{pseudo_id:04}"

    def get_pseudonym(self, patient_id: str) -> str | None:
        """Get the pseudonym generated for the given patient_id if a mapping exists"""

        pseudo_id = self._lookup_ix.get(patient_id)
        if not pseudo_id:
            return None
        return self._mk_pseudonym(pseudo_id)

    @lru_cache(maxsize=100)
    def get_or_assign_pseudonym(self, patient_id: str) -> str:
        """Get the pseudonym generated for the given patient_id if a mapping exists,
        else assign a new one"""

        pseudo_id = self.assign(patient_id)
        return self._mk_pseudonym(pseudo_id)

    def to_dict(self) -> dict[str, str]:
        return {
            patient_id: self._mk_pseudonym(pseudo_id)
            for patient_id, pseudo_id in self._lookup_ix.items()
            if patient_id != self._max_counter_name
        }
