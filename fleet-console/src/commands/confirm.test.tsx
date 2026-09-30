import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ConfirmationProblem } from '../api/types';
import { ConfirmDialog } from './ConfirmDialog';
import { HOLD_MS, HoldToConfirm } from './HoldToConfirm';

describe('HoldToConfirm (no risky command from a single keystroke or click)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function button(onConfirm: () => void) {
    render(<HoldToConfirm label="Confirm ARM (2)" onConfirm={onConfirm} />);
    return screen.getByRole('button', { name: /Confirm ARM \(2\)/ });
  }

  it('confirms after the pointer is held for the full time', () => {
    const onConfirm = vi.fn();
    const b = button(onConfirm);

    fireEvent.pointerDown(b);
    act(() => {
      vi.advanceTimersByTime(HOLD_MS - 1);
    });
    expect(onConfirm).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('confirms nothing when released early, or by a click', () => {
    const onConfirm = vi.fn();
    const b = button(onConfirm);

    fireEvent.pointerDown(b);
    act(() => {
      vi.advanceTimersByTime(HOLD_MS / 2);
    });
    fireEvent.pointerUp(b);
    fireEvent.click(b);
    act(() => {
      vi.advanceTimersByTime(HOLD_MS * 3);
    });

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('confirms nothing when the pointer leaves', () => {
    const onConfirm = vi.fn();
    const b = button(onConfirm);

    fireEvent.pointerDown(b);
    fireEvent.pointerLeave(b);
    act(() => {
      vi.advanceTimersByTime(HOLD_MS * 2);
    });

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('never confirms on Enter; holding Space for the full time does', () => {
    const onConfirm = vi.fn();
    const b = button(onConfirm);

    fireEvent.keyDown(b, { key: 'Enter' });
    act(() => {
      vi.advanceTimersByTime(HOLD_MS * 2);
    });
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.keyDown(b, { key: ' ' });
    fireEvent.keyUp(b, { key: ' ' }); // released at once: nothing
    act(() => {
      vi.advanceTimersByTime(HOLD_MS * 2);
    });
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.keyDown(b, { key: ' ' });
    act(() => {
      vi.advanceTimersByTime(HOLD_MS);
    });
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('does nothing while disabled', () => {
    const onConfirm = vi.fn();
    render(<HoldToConfirm label="Confirm" onConfirm={onConfirm} disabled />);
    fireEvent.pointerDown(screen.getByRole('button'));
    act(() => {
      vi.advanceTimersByTime(HOLD_MS * 2);
    });
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

function problem(overrides: Partial<ConfirmationProblem['summary']> = {}): ConfirmationProblem {
  return {
    type: 'urn:sar-gcs:problem:confirmation-required',
    title: 'Confirmation required',
    status: 428,
    detail: null,
    instance: null,
    command_id: 'c1',
    confirmation_token: 'tok',
    expires_at: '2026-09-30T00:00:30Z',
    summary: {
      kind: 'return_to_launch',
      params: {},
      reasons: ['sent to 2 aircraft'],
      override: false,
      aircraft: [
        { aircraft_id: 'a1', callsign: 'HX-01', warnings: ['battery 25 %'] },
        { aircraft_id: 'a2', callsign: 'HX-02', warnings: [] },
      ],
      rejected: [
        {
          aircraft_id: 'a3',
          callsign: 'HX-03',
          code: 'no-control',
          message: 'Take control first.',
        },
      ],
      conflicts: [],
      preflight: [],
      ...overrides,
    },
  };
}

describe('ConfirmDialog', () => {
  it("shows the server's summary and names the aircraft count", () => {
    render(
      <ConfirmDialog problem={problem()} busy={false} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );

    expect(
      screen.getByRole('heading', { name: 'RETURN TO LAUNCH 2 aircraft?' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/sent to 2 aircraft/)).toBeInTheDocument();
    expect(screen.getByText(/battery 25 %/)).toBeInTheDocument();
    expect(screen.getByText('1 will not be sent')).toBeInTheDocument();
    expect(screen.getByText(/Take control first\./)).toBeInTheDocument();
    expect(screen.queryByText(/Override/)).not.toBeInTheDocument();
  });

  it('flags an override', () => {
    render(
      <ConfirmDialog
        problem={problem({ override: true })}
        busy={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('note')).toHaveTextContent(/Override/);
  });

  it('starts with the focus on Cancel, and Cancel cancels', () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog problem={problem()} busy={false} onConfirm={onConfirm} onCancel={onCancel} />,
    );

    const cancel = screen.getByRole('button', { name: 'Cancel' });
    expect(cancel).toHaveFocus();
    fireEvent.click(cancel);

    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
