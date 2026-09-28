"""Tests for the standalone simulator CLI (arguments, report, CSV, chart and animation)."""

import csv

import pytest
from swarm_sar import standalone
from swarm_sar.core.metrics import CSV_COLUMNS

SMALL = ['--area-size', '30', '--transit-distance', '10', '--tree-density', '40']


def test_bad_arguments_exit_with_code_2(capsys):
    assert standalone.main(['--num-drones', '0', '--no-video']) == 2
    assert standalone.main(['--max-speed', 'abc', '--no-video']) == 2
    assert standalone.main(['--track-standoff', '99', '--no-video']) == 2
    assert standalone.main(['--seed', '-1', '--no-video']) == 2
    assert standalone.main(['--out', 'movie.avi']) == 2
    assert standalone.main(['--depth-stride', '4', '--no-video']) == 2  # too coarse for the sim
    assert 'error:' in capsys.readouterr().err


def test_missing_output_directory_fails_before_simulating(tmp_path, capsys):
    missing = tmp_path / 'nope' / 'run.csv'
    assert standalone.main(['--no-video', '--duration', '1000', '--metrics-csv',
                            str(missing)]) == 2
    assert 'does not exist' in capsys.readouterr().err


def test_headless_run_writes_csv_and_report(tmp_path, capsys):
    out = tmp_path / 'run.csv'
    code = standalone.main(['--num-drones', '2', '--duration', '3', '--no-video',
                            '--metrics-csv', str(out)] + SMALL)
    assert code == 0
    text = capsys.readouterr().out
    assert 'area explored' in text and 'closest tree' in text and 'collisions' in text
    with open(out, newline='', encoding='utf-8') as handle:
        rows = list(csv.reader(handle))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert len(rows) == 1 + 30  # one row per 0.1 s control period


def test_metrics_chart_is_rendered(tmp_path):
    pytest.importorskip('matplotlib')
    chart = tmp_path / 'metrics.png'
    code = standalone.main(['--num-drones', '2', '--duration', '3', '--no-video',
                            '--metrics-plot', str(chart)] + SMALL)
    assert code == 0 and chart.stat().st_size > 10_000


def test_gif_animation_is_rendered(tmp_path):
    pytest.importorskip('matplotlib')
    movie = tmp_path / 'demo.gif'
    code = standalone.main(['--num-drones', '2', '--duration', '2', '--frame-every', '1.0',
                            '--out', str(movie)] + SMALL)
    assert code == 0 and movie.stat().st_size > 10_000
