export type Point={x:number;y:number}; export type Box={x:number;y:number;width:number;height:number};
export function canvasToImageCoordinates(point:Point, scale:number):Point { return {x:point.x/scale,y:point.y/scale}; }
export function imageToCanvasCoordinates(point:Point, scale:number):Point { return {x:point.x*scale,y:point.y*scale}; }
export function clampBox(box:Box, width:number,height:number):Box { const x=Math.max(0,Math.min(box.x,width)); const y=Math.max(0,Math.min(box.y,height)); return {...box,x,y,width:Math.max(1,Math.min(box.width,width-x)),height:Math.max(1,Math.min(box.height,height-y))}; }
