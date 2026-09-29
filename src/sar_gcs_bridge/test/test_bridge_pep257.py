"""ament_pep257 docstring check (runs under colcon test; skipped without ament_pep257)."""

import pytest


@pytest.mark.linter
@pytest.mark.pep257
def test_pep257():
    main = pytest.importorskip('ament_pep257.main').main
    assert main(argv=['.', 'test']) == 0, 'Found code style errors / warnings'
