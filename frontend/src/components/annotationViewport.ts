import type {Point} from '../types';

export type Dimensions = {width: number; height: number};
export type Viewport = {scale: number; offsetX: number; offsetY: number};

export function imageToScreen([x, y]: Point, view: Viewport): Point {
  return [x * view.scale + view.offsetX, y * view.scale + view.offsetY];
}

/** Coordinates here are local CSS pixels, never canvas backing/device pixels. */
export function screenToImage([x, y]: Point, view: Viewport): Point {
  return [(x - view.offsetX) / view.scale, (y - view.offsetY) / view.scale];
}

export function fitScale(image: Dimensions, workspace: Dimensions): number {
  return workspace.width > 0 && workspace.height > 0
    ? Math.min(workspace.width / image.width, workspace.height / image.height) : 1;
}

export function centeredViewport(image: Dimensions, workspace: Dimensions, scale = 1): Viewport {
  return {scale, offsetX: workspace.width > 0 ? (workspace.width - image.width * scale) / 2 : 0,
    offsetY: workspace.height > 0 ? (workspace.height - image.height * scale) / 2 : 0};
}

export function fitViewport(image: Dimensions, workspace: Dimensions): Viewport {
  return centeredViewport(image, workspace, fitScale(image, workspace));
}

export function zoomViewport(view: Viewport, anchor: Point, requestedScale: number, image: Dimensions, workspace: Dimensions): Viewport {
  const fit = fitScale(image, workspace);
  // Fit remains reachable even for enormous images; tiny images may fit above 800%.
  const scale = Math.max(Math.min(0.05, fit), Math.min(Math.max(8, fit), requestedScale));
  const [x, y] = screenToImage(anchor, view);
  return {scale, offsetX: anchor[0] - x * scale, offsetY: anchor[1] - y * scale};
}

export function resizedViewport(view: Viewport, previous: Dimensions, next: Dimensions): Viewport {
  return {...view, offsetX: view.offsetX + (next.width - previous.width) / 2,
    offsetY: view.offsetY + (next.height - previous.height) / 2};
}

export function clampImagePoint([x, y]: Point, image: Dimensions): Point {
  return [Math.max(0, Math.min(image.width, x)), Math.max(0, Math.min(image.height, y))];
}
