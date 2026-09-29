"""ament_flake8 style check (runs under colcon test; skipped without ament_flake8)."""

import pytest


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    main_with_errors = pytest.importorskip('ament_flake8.main').main_with_errors
    rc, errors = main_with_errors(argv=[])
    assert rc == 0, f'Found {len(errors)} code style errors / warnings:\n' + '\n'.join(errors)
