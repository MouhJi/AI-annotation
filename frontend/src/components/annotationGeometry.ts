import type {DraftAnnotation,Point} from '../types';
export function moveGeometry(a:DraftAnnotation,dx:number,dy:number,w:number,h:number,handle='move',vertex?:number):Partial<DraftAnnotation>{
 const clamp=(n:number,min:number,max:number)=>Math.max(min,Math.min(max,n));
 if(a.annotation_type==='polygon'&&a.points){
  let points:Point[];
  if(vertex!==undefined)points=a.points.map((p,i)=>i===vertex?[clamp(p[0]+dx,0,w),clamp(p[1]+dy,0,h)]:p);
  else{dx=clamp(dx,-a.x,w-a.x-a.width);dy=clamp(dy,-a.y,h-a.y-a.height);points=a.points.map(p=>[p[0]+dx,p[1]+dy])}
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);return {points,x:Math.min(...xs),y:Math.min(...ys),width:Math.max(...xs)-Math.min(...xs),height:Math.max(...ys)-Math.min(...ys)};
 }
 if(handle==='move')return {x:clamp(a.x+dx,0,w-a.width),y:clamp(a.y+dy,0,h-a.height)};
 let l=a.x,t=a.y,r=a.x+a.width,b=a.y+a.height;
 if(handle.includes('w'))l=clamp(l+dx,0,r-1);if(handle.includes('e'))r=clamp(r+dx,l+1,w);
 if(handle.includes('n'))t=clamp(t+dy,0,b-1);if(handle.includes('s'))b=clamp(b+dy,t+1,h);
 return {x:l,y:t,width:r-l,height:b-t};
}
