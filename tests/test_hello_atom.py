"""Hello atom dry-run: the full atom pipe (input -> 'model' -> schema validation -> output)"""

from process_twin.runtime.atoms import get_atom, register_atom, run_hello_atom
from process_twin.schemas.runtime import AtomInput, AtomOutput


def test_dry_run_produces_valid_atom_output():
    output, cost = run_hello_atom(dry_run=True, trace=None)
    assert isinstance(output, AtomOutput)
    assert "greeting" in output.result
    assert 0.0 <= output.confidence <= 1.0
    assert output.needs_human is False
    assert cost == 0.0


def test_registry_rejects_duplicates_and_unknown_lookups():
    import pytest

    @register_atom("test_atom_unique_xyz")
    def _atom(inp: AtomInput) -> AtomOutput:  # pragma: no cover - registration is the test
        return AtomOutput(result={}, confidence=1.0)

    assert get_atom("test_atom_unique_xyz") is _atom
    with pytest.raises(ValueError):
        register_atom("test_atom_unique_xyz")(_atom)
    with pytest.raises(KeyError):
        get_atom("never_registered")
