// Plays the alert cues (cues.ts) with WebAudio. Browsers only allow sound after the operator
// has interacted with the page, which signing in does. Muting is a per-browser preference.
import { useEffect } from 'react';
import { create } from 'zustand';

import type { AlertView } from '../api/types';
import { useLive } from '../live/store';
import { type Cue, criticalActive, cueFor, REMIND_MS, TONES } from './cues';

const MUTE_KEY = 'sargcs.mute';

function storedMute(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === '1';
  } catch {
    return false;
  }
}

export const useSound = create<{ muted: boolean; toggle: () => void }>()((set) => ({
  muted: storedMute(),
  toggle: () => {
    set((s) => {
      try {
        localStorage.setItem(MUTE_KEY, s.muted ? '0' : '1');
      } catch {
        // storage unavailable: the choice lasts until reload
      }
      return { muted: !s.muted };
    });
  },
}));

let context: AudioContext | null = null;

function play(cue: Cue): void {
  if (useSound.getState().muted) return;
  try {
    context ??= new AudioContext();
    let t = context.currentTime;
    for (const [frequency, duration, pause] of TONES[cue]) {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.frequency.value = frequency;
      oscillator.type = 'square';
      gain.gain.setValueAtTime(0.08, t);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + duration / 1000);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(t);
      oscillator.stop(t + duration / 1000);
      t += (duration + pause) / 1000;
    }
  } catch {
    // no audio device or API: the alerts are still on screen
  }
}

/** Cue new and escalated alerts, and remind while a critical alert is unacknowledged. */
export function useAlertCues(): void {
  useEffect(() => {
    // null: the next alert update is a (re)connection's snapshot, the backlog: no replay.
    let previous: Record<string, AlertView> | null = null;
    let lastCue = 0;
    const unsubscribe = useLive.subscribe((state, prior) => {
      if (state.connection !== prior.connection && state.connection !== 'online') {
        previous = null;
      }
      if (state.alerts === prior.alerts) return;
      const cue = state.connection === 'online' ? cueFor(previous, state.alerts) : null;
      previous = state.connection === 'online' ? state.alerts : null;
      if (cue) {
        lastCue = Date.now();
        play(cue);
      }
    });
    const reminder = window.setInterval(() => {
      const { alerts } = useLive.getState();
      if (criticalActive(alerts) && Date.now() - lastCue >= REMIND_MS) {
        lastCue = Date.now();
        play('critical');
      }
    }, 5_000);
    return () => {
      unsubscribe();
      window.clearInterval(reminder);
    };
  }, []);
}
