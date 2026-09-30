// Aircraft icons, drawn at runtime as signed-distance-field images (tinted per link state by
// the map). Pointing north; the map rotates them by heading. See symbology.ts.
import type { Kind, Shape } from './symbology';

export const ICON_SIZE = 64; // drawn at 2x, shown at 32 CSS pixels
export const ICON_PIXEL_RATIO = 2;

function planePath(ctx: CanvasRenderingContext2D, s: number): void {
  // A simple top-down plane: nose at the top.
  const c = s / 2;
  ctx.beginPath();
  ctx.moveTo(c, 6);
  ctx.lineTo(c + 5, 24);
  ctx.lineTo(s - 6, 34);
  ctx.lineTo(s - 6, 40);
  ctx.lineTo(c + 5, 36);
  ctx.lineTo(c + 4, 50);
  ctx.lineTo(c + 11, 56);
  ctx.lineTo(c - 11, 56);
  ctx.lineTo(c - 4, 50);
  ctx.lineTo(c - 5, 36);
  ctx.lineTo(6, 40);
  ctx.lineTo(6, 34);
  ctx.lineTo(c - 5, 24);
  ctx.closePath();
}

function diamondPath(ctx: CanvasRenderingContext2D, s: number): void {
  const c = s / 2;
  ctx.beginPath();
  ctx.moveTo(c, 10);
  ctx.lineTo(s - 10, c);
  ctx.lineTo(c, s - 10);
  ctx.lineTo(10, c);
  ctx.closePath();
}

/** Draw one icon; `hasHeading` false draws a shape with no direction. */
export function drawIcon(kind: Kind, shape: Shape, hasHeading: boolean): ImageData {
  const s = ICON_SIZE;
  const canvas = document.createElement('canvas');
  canvas.width = s;
  canvas.height = s;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('no 2D canvas');
  ctx.fillStyle = '#fff';
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 5;
  ctx.lineJoin = 'round';

  if (kind === 'fixed-wing') {
    if (hasHeading) planePath(ctx, s);
    else diamondPath(ctx, s);
  } else {
    ctx.beginPath();
    ctx.arc(s / 2, s / 2 + 4, 18, 0, Math.PI * 2);
  }
  if (shape === 'solid') ctx.fill();
  else ctx.stroke();

  if (kind === 'multirotor' && hasHeading) {
    // the nose: a triangle ahead of the body
    ctx.beginPath();
    ctx.moveTo(s / 2, 2);
    ctx.lineTo(s / 2 + 9, 16);
    ctx.lineTo(s / 2 - 9, 16);
    ctx.closePath();
    ctx.fill();
  }
  if (shape === 'crossed') {
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(18, 22);
    ctx.lineTo(s - 18, s - 14);
    ctx.moveTo(s - 18, 22);
    ctx.lineTo(18, s - 14);
    ctx.stroke();
  }
  return ctx.getImageData(0, 0, s, s);
}
