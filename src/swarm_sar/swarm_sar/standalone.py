"""
Run the swarm in the CPU-only forest simulator and render the result.

    swarm_sar_sim --num-drones 8 --duration 180 --out demo.mp4
    swarm_sar_sim --no-video --metrics-csv run.csv --metrics-plot run.png

The flight code is exactly what runs on the drones (``DroneController``);
the world (trees, target, radio, PX4-like autopilot, synthetic depth camera)
is simulated. Every drone and world option is generated from the config
dataclasses (``--max-speed``, ``--tree-density``, ...; see ``--help``).
In simulation ``--depth-stride`` defaults to 1 because the synthetic camera
renders a small image. Exit codes: 0 success, 2 invalid arguments or missing
dependency.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import pathlib
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

from swarm_sar.core.config import (config_fields, config_from_text, ConfigError, DroneConfig,
                                   format_value, SimConfig)
from swarm_sar.core.messages import Phase
from swarm_sar.core.metrics import CSV_COLUMNS, csv_row, MetricsSnapshot
from swarm_sar.sim.simulation import (check_sim_arguments, Frame, MAX_SIM_DRONES, SimReport,
                                      Simulation)

SIM_DEFAULTS: Dict[str, str] = {'depth_stride': '1'}

# Colours from the data-viz reference palette (light mode). Roles, not decoration:
SURFACE = '#fcfcfb'
INK = '#0b0b0b'            # primary text; searching drones
INK_SECONDARY = '#52514e'  # secondary text
INK_MUTED = '#898781'      # axis labels, trees (context)
HAIRLINE = '#e1e0d9'       # grid lines
AXIS = '#c3c2b7'           # axes, area outline, route, camera view cones
CONE_ALPHA = 0.45
TRACK_COLOR = '#eb6834'    # categorical slot 2: tracking drones and their estimate
TARGET_COLOR = '#1baf7a'   # categorical slot 3: ground-truth target (always direct-labelled)
SERIES_COLOR = '#2a78d6'   # categorical slot 1: the single series of each metrics panel
SEARCHED_RAMP = ('#fcfcfb', '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5')  # sequential blue


class UsageError(Exception):
    """Invalid command-line usage or a missing optional dependency."""


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI; config options are generated from the dataclasses."""
    parser = argparse.ArgumentParser(prog='swarm_sar_sim', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    run = parser.add_argument_group('run')
    run.add_argument('--num-drones', type=int, default=8)
    run.add_argument('--seed', type=int, default=2)
    run.add_argument('--duration', type=float, default=180.0, help='simulated seconds')
    run.add_argument('--out', default='swarm_sar_demo.mp4', help='.mp4 (needs ffmpeg) or .gif')
    run.add_argument('--no-video', action='store_true', help='skip rendering the animation')
    run.add_argument('--fps', type=int, default=15)
    run.add_argument('--frame-every', type=float, default=0.5,
                     help='simulated seconds between animation frames')
    run.add_argument('--metrics-csv', default='', help='write per-step metrics to this CSV')
    run.add_argument('--metrics-plot', default='', help='write a metrics chart (PNG) here')
    for cls, title in ((DroneConfig, 'drone'), (SimConfig, 'world')):
        group = parser.add_argument_group(title)
        for spec in config_fields(cls):
            default = SIM_DEFAULTS.get(spec.name, format_value(spec.default))
            group.add_argument('--' + spec.name.replace('_', '-'), dest=spec.name, default=None,
                               metavar='VALUE', help=f'{spec.description} (default {default})')
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI; return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        overrides = dict(SIM_DEFAULTS)
        overrides.update({k: v for k, v in vars(args).items() if isinstance(v, str)})
        drone = config_from_text(DroneConfig, overrides)
        world = config_from_text(SimConfig, overrides)
        _check_run_arguments(args)
        sim = Simulation(drone, world, args.num_drones, args.seed)
    except (ConfigError, UsageError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    for note in drone.warnings():
        print(f'warning: {note}', file=sys.stderr)

    stride = max(1, round(args.frame_every / drone.control_period))
    snapshots: List[MetricsSnapshot] = []
    frames: List[Frame] = []

    def on_step(simulation: Simulation, snapshot: MetricsSnapshot) -> None:
        snapshots.append(snapshot)
        if not args.no_video and (len(snapshots) - 1) % stride == 0:
            frames.append(simulation.frame())

    started = time.perf_counter()
    report = sim.run(args.duration, on_step)
    print(format_report(report, args.num_drones, time.perf_counter() - started))
    if args.metrics_csv:
        write_csv(args.metrics_csv, snapshots)
        print(f'metrics CSV: {args.metrics_csv}')
    if args.metrics_plot:
        render_metrics(snapshots, report, drone, args.metrics_plot)
        print(f'metrics chart: {args.metrics_plot}')
    if not args.no_video:
        render_animation(frames, sim, args.out, args.fps)
        print(f'animation: {args.out}')
    return 0


def _check_run_arguments(args: argparse.Namespace) -> None:
    try:
        check_sim_arguments(args.num_drones, args.duration)
    except ConfigError as exc:
        raise UsageError(str(exc)) from exc
    if not 1 <= args.num_drones <= MAX_SIM_DRONES:
        raise UsageError(f'--num-drones must be in [1, {MAX_SIM_DRONES}]')
    if args.seed < 0:
        raise UsageError('--seed must be non-negative')
    if args.fps < 1 or not (math.isfinite(args.frame_every) and args.frame_every > 0):
        raise UsageError('--fps must be >= 1 and --frame-every positive')
    outputs = [args.metrics_csv, args.metrics_plot] + ([] if args.no_video else [args.out])
    for output in filter(None, outputs):
        if not pathlib.Path(output).resolve().parent.is_dir():
            raise UsageError(f'output directory for {output!r} does not exist')
    if args.metrics_plot or not args.no_video:
        _pyplot()  # fail fast, before a long simulation, if matplotlib is missing
    if not args.no_video:
        suffix = pathlib.Path(args.out).suffix.lower()
        if suffix not in ('.mp4', '.gif'):
            raise UsageError('--out must end in .mp4 or .gif')
        if suffix == '.mp4' and shutil.which('ffmpeg') is None:
            raise UsageError('ffmpeg is needed for .mp4 output; install it or use --out x.gif')


def format_report(report: SimReport, num_drones: int, wall_seconds: float) -> str:
    """Return a human-readable mission report."""
    s = report.summary

    def fmt(value: Optional[float], unit: str, scale: float = 1.0) -> str:
        return 'n/a' if value is None or not math.isfinite(value) else \
            f'{value * scale:.1f}{unit}'
    milestones = ', '.join(f'{int(100 * k)}% at {fmt(v, " s")}'
                           for k, v in sorted(s.time_to_explored.items()))
    return '\n'.join((
        f'simulated {s.mission_time:.1f} s with {num_drones} drones '
        f'in {wall_seconds:.1f} s wall time',
        f'  area explored        {fmt(s.explored_fraction, "%", 100.0)} ({milestones})',
        f'  target first found   {fmt(s.time_to_first_detection, " s")}',
        f'  mean tracking error  {fmt(s.mean_tracking_error, " m")}',
        f'  track continuity     {fmt(s.track_continuity, "%", 100.0)}',
        f'  closest drones       {fmt(report.min_true_separation, " m")}',
        f'  closest tree         {fmt(report.min_tree_clearance, " m")} (surface)',
        f'  collisions           {report.tree_collisions} tree, {report.drone_collisions} drone',
        f'  autopilot failsafes  {report.failsafes}'))


def write_csv(path: str, snapshots: Sequence[MetricsSnapshot]) -> None:
    """Write one row per simulation step."""
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(csv_row(s) for s in snapshots)


def _pyplot() -> Any:
    try:
        import matplotlib
    except ImportError as exc:
        raise UsageError('rendering needs matplotlib (pip install matplotlib) or use '
                         '--no-video') from exc
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def _style_axes(ax: Any) -> None:
    ax.set_facecolor(SURFACE)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(1.0)
    ax.tick_params(colors=INK_MUTED, labelsize=9, length=3, width=1.0)


def render_animation(frames: Sequence[Frame], sim: Simulation, out: str, fps: int) -> None:
    """Render frames to MP4/GIF: forest, area, coverage, drones with camera cones, target."""
    if not frames:
        raise UsageError('nothing to render (duration shorter than one frame)')
    plt = _pyplot()
    import numpy as np
    from matplotlib import animation, patheffects
    from matplotlib.collections import PatchCollection, PolyCollection
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle, Ellipse, Polygon

    plan = sim.plan
    geometry = plan.geometry
    cfg = sim.drone_config
    points = list(plan.area) + list(plan.waypoints) + [(0.0, 0.0)]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    margin = 8.0
    fig = plt.figure(figsize=(11.2, 7.2), dpi=100, facecolor=SURFACE)
    ax = fig.add_axes((0.05, 0.08, 0.62, 0.86))
    panel = fig.add_axes((0.69, 0.08, 0.29, 0.86))
    panel.axis('off')
    _style_axes(ax)
    ax.set_xlim(min(xs) - margin, max(xs) + margin)
    ax.set_ylim(min(ys) - margin, max(ys) + margin)
    ax.set_aspect('equal')
    ax.set_xlabel('east [m]', color=INK_MUTED, fontsize=9)
    ax.set_ylabel('north [m]', color=INK_MUTED, fontsize=9)

    cmap = LinearSegmentedColormap.from_list('searched', SEARCHED_RAMP)
    cmap.set_bad(SURFACE, alpha=0.0)
    b = geometry.bounds
    extent = (b.xmin, b.xmin + geometry.nx * geometry.cell_size,
              b.ymin, b.ymin + geometry.ny * geometry.cell_size)
    heat = ax.imshow(np.zeros(geometry.shape).T, origin='lower', extent=extent, cmap=cmap,
                     vmin=0.0, vmax=1.0, interpolation='nearest', zorder=0)
    ax.add_patch(Polygon(plan.area, closed=True, fill=False, edgecolor=AXIS, linewidth=1.2,
                         zorder=1))
    if plan.waypoints:
        route = [(0.0, 0.0)] + list(plan.waypoints)
        ax.plot([p[0] for p in route], [p[1] for p in route], color=AXIS, linewidth=1.0,
                linestyle='--', zorder=1)
    trees = PatchCollection([Circle(tuple(c), r) for c, r in
                             zip(sim.forest.centers, sim.forest.radii)],
                            facecolor=INK_MUTED, edgecolor='none', alpha=0.8, zorder=2)
    ax.add_collection(trees)
    cones = PolyCollection([], facecolors=AXIS, edgecolors='none', alpha=CONE_ALPHA, zorder=1)
    ax.add_collection(cones)
    searchers = ax.scatter([], [], s=30, c=INK, edgecolors=SURFACE, linewidths=1.2, zorder=5)
    trackers = ax.scatter([], [], s=52, c=TRACK_COLOR, edgecolors=SURFACE, linewidths=1.5,
                          zorder=6)
    holding = ax.scatter([], [], s=40, facecolors='none', edgecolors=INK, linewidths=1.5,
                         zorder=6)
    ellipse = Ellipse((0.0, 0.0), 1.0, 1.0, fill=False, edgecolor=TRACK_COLOR, linewidth=1.8,
                      zorder=4, visible=False)
    ax.add_patch(ellipse)
    target = ax.scatter([], [], s=220, marker='*', c=TARGET_COLOR, edgecolors=SURFACE,
                        linewidths=1.2, zorder=7)
    target_label = ax.text(0.0, 0.0, 'target', color=INK, fontsize=9, zorder=8, ha='left',
                           va='bottom',
                           path_effects=[patheffects.withStroke(linewidth=3.0,
                                                                foreground=SURFACE)])

    panel.text(0.0, 1.0, 'SAR swarm in a forest', color=INK, fontsize=14,
               fontweight='semibold', va='top', transform=panel.transAxes)
    panel.text(0.0, 0.955, f'{len(frames[0].drones)} drones, {len(sim.forest)} trees\n'
               f'depth-camera avoidance, max {cfg.max_speed:g} m/s',
               color=INK_SECONDARY, fontsize=9, va='top', linespacing=1.4,
               transform=panel.transAxes)
    tiles = {}
    for row, (key, label) in enumerate((('time', 'Mission time'), ('explored', 'Area explored'),
                                        ('found', 'Target'), ('error', 'Tracking error'),
                                        ('phases', 'Transit / search / track / hold'))):
        y = 0.86 - row * 0.105
        panel.text(0.0, y, label, color=INK_SECONDARY, fontsize=9, va='top',
                   transform=panel.transAxes)
        tiles[key] = panel.text(0.0, y - 0.03, '', color=INK, fontsize=16,
                                fontweight='semibold', va='top', transform=panel.transAxes)
    legend_handles = [
        Line2D([], [], marker='o', linestyle='', markersize=6, markerfacecolor=INK,
               markeredgecolor=SURFACE, label='Drone in transit or searching'),
        Line2D([], [], marker='o', linestyle='', markersize=8, markerfacecolor=TRACK_COLOR,
               markeredgecolor=SURFACE, label='Drone tracking the target'),
        Line2D([], [], marker='o', linestyle='', markersize=7, markerfacecolor='none',
               markeredgecolor=INK, label='Drone holding'),
        Line2D([], [], color=AXIS, alpha=CONE_ALPHA, linewidth=6.0, label='Depth camera view'),
        Line2D([], [], marker='o', linestyle='', markersize=6, markerfacecolor=INK_MUTED,
               markeredgecolor='none', label='Tree trunk'),
        Line2D([], [], color=TRACK_COLOR, linewidth=1.8, label='Target estimate (2σ)'),
        Line2D([], [], marker='*', linestyle='', markersize=12, markerfacecolor=TARGET_COLOR,
               markeredgecolor=SURFACE, label='Target (ground truth)'),
        Line2D([], [], color=AXIS, linewidth=1.2, label='Search area, transit route'),
    ]
    panel.legend(handles=legend_handles, loc='upper left', bbox_to_anchor=(0.0, 0.33),
                 frameon=False, fontsize=9, labelcolor=INK_SECONDARY, handletextpad=0.6,
                 borderaxespad=0.0)
    bar_ax = fig.add_axes((0.69, 0.07, 0.22, 0.016))
    gradient = np.linspace(0.0, 1.0, 256)[None, :]
    bar_ax.imshow(gradient, aspect='auto', cmap=cmap, extent=(0.0, 1.0, 0.0, 1.0))
    bar_ax.set_yticks([])
    bar_ax.set_xticks([0.0, 1.0])
    stale_label, fresh_label = bar_ax.set_xticklabels(
        [f'≥ {cfg.revisit_period:.0f} s ago or never', 'just now'])
    stale_label.set_horizontalalignment('left')
    fresh_label.set_horizontalalignment('right')
    bar_ax.tick_params(colors=INK_MUTED, labelsize=8, length=0)
    for spine in bar_ax.spines.values():
        spine.set_visible(False)
    fig.text(0.69, 0.092, 'Searched', color=INK_SECONDARY, fontsize=9)
    half_fov = math.radians(sim.sim_config.camera_hfov_deg) / 2.0
    camera_yaw = -math.radians(cfg.camera_rpy_deg[2])  # FRD yaw is clockwise
    cone_length = cfg.depth_trusted_range

    def draw(index: int) -> List[Any]:
        frame = frames[index]
        staleness = np.clip((frame.time - frame.explored) / cfg.revisit_period, 0.0, 1.0)
        shown = np.where(geometry.valid, 1.0 - staleness, np.nan)
        heat.set_data(shown.T)
        moving = [d for d in frame.drones if d.phase in (Phase.TRANSIT, Phase.SEARCH)]
        track = [d for d in frame.drones if d.phase is Phase.TRACK]
        idle = [d for d in frame.drones if d.phase in (Phase.HOLD, Phase.STANDBY)]
        for artist, group in ((searchers, moving), (trackers, track), (holding, idle)):
            artist.set_offsets(np.array([d.position for d in group]).reshape(-1, 2))
        cones.set_verts([
            [d.position,
             (d.position[0] + cone_length * math.cos(d.heading + camera_yaw - half_fov),
              d.position[1] + cone_length * math.sin(d.heading + camera_yaw - half_fov)),
             (d.position[0] + cone_length * math.cos(d.heading + camera_yaw + half_fov),
              d.position[1] + cone_length * math.sin(d.heading + camera_yaw + half_fov))]
            for d in frame.drones])
        estimates = [(d.estimate_position, d.estimate_covariance) for d in frame.drones
                     if d.estimate_position is not None and d.estimate_covariance is not None]
        if estimates:
            centre, covariance = min(estimates,
                                     key=lambda e: float(np.linalg.eigvalsh(e[1])[-1]))
            values, vectors = np.linalg.eigh(covariance)
            ellipse.set_center(centre)
            ellipse.set_width(4.0 * math.sqrt(max(values[1], 0.0)))
            ellipse.set_height(4.0 * math.sqrt(max(values[0], 0.0)))
            ellipse.set_angle(math.degrees(math.atan2(vectors[1, 1], vectors[0, 1])))
            ellipse.set_visible(True)
        else:
            ellipse.set_visible(False)
        target.set_offsets([frame.target])
        target_label.set_position((frame.target[0] + 2.0, frame.target[1] + 2.0))
        m = frame.metrics
        counts = [sum(1 for d in frame.drones if d.phase is p)
                  for p in (Phase.TRANSIT, Phase.SEARCH, Phase.TRACK, Phase.HOLD)]
        tiles['time'].set_text(f'{frame.time:.0f} s')
        tiles['explored'].set_text(f'{100.0 * m.explored_fraction:.0f}%')
        tiles['found'].set_text('searching…' if m.time_to_first_detection is None
                                else f'found at {m.time_to_first_detection:.0f} s')
        tiles['error'].set_text('–' if m.tracking_error is None else f'{m.tracking_error:.1f} m')
        tiles['phases'].set_text(' / '.join(str(c) for c in counts))
        return [heat, cones, searchers, trackers, holding, ellipse, target, target_label,
                *tiles.values()]

    movie = animation.FuncAnimation(fig, draw, frames=len(frames), interval=1000.0 / fps,
                                    blit=False)
    writer: Any
    if pathlib.Path(out).suffix.lower() == '.gif':
        writer = animation.PillowWriter(fps=fps)
    else:
        writer = animation.FFMpegWriter(fps=fps, bitrate=2400,
                                        extra_args=['-pix_fmt', 'yuv420p'])
    movie.save(out, writer=writer, savefig_kwargs={'facecolor': SURFACE})
    plt.close(fig)


def render_metrics(snapshots: Sequence[MetricsSnapshot], report: SimReport,
                   config: DroneConfig, out: str) -> None:
    """Render three small multiples sharing the time axis (never a dual-axis chart)."""
    if not snapshots:
        raise UsageError('no metrics to plot')
    plt = _pyplot()
    times = [s.mission_time for s in snapshots]
    explored = [100.0 * s.explored_fraction for s in snapshots]
    errors = [math.nan if s.tracking_error is None else s.tracking_error for s in snapshots]
    nearest = [math.nan if s.min_obstacle_distance is None else s.min_obstacle_distance
               for s in snapshots]
    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(8.0, 7.5), dpi=120,
                             facecolor=SURFACE)
    panels = (
        (axes[0], explored, 'Area explored', '%', ''),
        (axes[1], errors, 'Tracking error (best estimate vs truth)', 'm', ''),
        (axes[2], nearest, 'Nearest obstacle any drone sees', 'm',
         f'gray line: obstacle_clearance = {config.obstacle_clearance:.1f} m'),
    )
    for ax, values, title, unit, note in panels:
        _style_axes(ax)
        ax.set_title(title, loc='left', color=INK, fontsize=11, fontweight='semibold', pad=6)
        if note:  # reference-line keys live in the header, never on top of the data
            ax.set_title(note, loc='right', color=INK_MUTED, fontsize=8, pad=6)
        ax.set_ylabel(unit, color=INK_MUTED, fontsize=9)
        ax.grid(axis='y', color=HAIRLINE, linewidth=1.0)
        ax.set_axisbelow(True)
        ax.plot(times, values, color=SERIES_COLOR, linewidth=2.0, solid_capstyle='round',
                zorder=3)
    axes[0].fill_between(times, explored, color=SERIES_COLOR, alpha=0.10, linewidth=0.0)
    axes[0].set_ylim(0.0, 100.0)
    axes[1].set_ylim(bottom=0.0)
    axes[2].set_ylim(bottom=0.0)
    axes[2].axhline(config.obstacle_clearance, color=INK_MUTED, linewidth=1.0, zorder=2)
    axes[2].set_xlim(0.0, max(times[-1], 1e-6))
    axes[2].set_xlabel('mission time [s]', color=INK_MUTED, fontsize=9)
    found = report.summary.time_to_first_detection
    if found is not None:
        for ax in axes:
            ax.axvline(found, color=AXIS, linewidth=1.0)
        axes[0].annotate(f'target found at {found:.0f} s', (found, 4.0), xytext=(4, 0),
                         textcoords='offset points', color=INK_SECONDARY, fontsize=8)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def cli() -> int:
    """Console entry point: like ``main`` but quiet when stdout is closed early (``| head``)."""
    try:
        return main()
    except BrokenPipeError:
        # Point stdout at /dev/null so the interpreter's final flush cannot fail again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1


if __name__ == '__main__':
    sys.exit(cli())
