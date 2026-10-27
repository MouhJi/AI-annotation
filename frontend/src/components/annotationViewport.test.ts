import {describe, expect, it} from 'vitest';
import {centeredViewport, clampImagePoint, fitViewport, imageToScreen, resizedViewport, screenToImage, zoomViewport} from './annotationViewport';

describe('image viewport coordinates', () => {
  for (const scale of [0.0001, 0.25, 1, 2, 4, 8]) it(`round trips original pixels at scale ${scale}`, () => {
    const view = {scale, offsetX:-137.42, offsetY:63.19};
    const point: [number, number] = [213.1234567, 98.7654321];
    const result = screenToImage(imageToScreen(point, view), view);
    expect(result[0]).toBeCloseTo(point[0], 7);
    expect(result[1]).toBeCloseTo(point[1], 7);
  });
  it('keeps the pixel under the cursor fixed through repeated zooms without rounding', () => {
    const image={width:4000,height:3000}, workspace={width:800,height:500};
    let view=fitViewport(image,workspace);
    const anchor: [number,number]=[219.37,173.84], original=screenToImage(anchor,view);
    for(let i=0;i<100;i++) {
      view=zoomViewport(view,anchor,view.scale*1.13,image,workspace);
      view=zoomViewport(view,anchor,view.scale/1.13,image,workspace);
    }
    expect(screenToImage(anchor,view)[0]).toBeCloseTo(original[0],10);
    expect(screenToImage(anchor,view)[1]).toBeCloseTo(original[1],10);
  });
  it('distinguishes native 100% from centered fit and allows fitting enormous images', () => {
    const image={width:100000,height:80000},workspace={width:800,height:500};
    const fit=fitViewport(image,workspace);
    expect(fit).toEqual({scale:0.00625,offsetX:87.5,offsetY:0});
    expect(centeredViewport(image,workspace)).toEqual({scale:1,offsetX:-49600,offsetY:-39750});
    expect(zoomViewport(fit,[0,0],0.0000001,image,workspace).scale).toBe(fit.scale);
    expect(zoomViewport(fit,[0,0],100,image,workspace).scale).toBe(8);
  });
  it('fits a small image proportionally and preserves the center during manual resize', () => {
    const image={width:100,height:50},before={width:800,height:500},after={width:600,height:400};
    expect(fitViewport(image,before)).toEqual({scale:8,offsetX:0,offsetY:50});
    const view={scale:4,offsetX:-160,offsetY:31};
    expect(screenToImage([300,200],resizedViewport(view,before,after))).toEqual(screenToImage([400,250],view));
    expect(clampImagePoint([-10,300],image)).toEqual([0,50]);
  });
});
