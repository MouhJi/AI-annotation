// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import AnnotationCanvas from './AnnotationCanvas';
import {imageToScreen, type Viewport} from './annotationViewport';
import type {ComponentProps} from 'react';

vi.mock('./ProtectedImage',()=>({default:({onLoadFailure,...props}:any)=><img {...props}/>}));
let bounds={left:70,top:120,width:800,height:500};
beforeEach(()=>{
  vi.stubGlobal('PointerEvent',MouseEvent);
  bounds={left:70,top:120,width:800,height:500};
  vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
    return (this.classList.contains('annotation-viewport')?bounds:{left:0,top:0,width:0,height:0}) as DOMRect;
  });
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
function setup(overrides:Partial<ComponentProps<typeof AnnotationCanvas>>={},width=1000,height=800){
  const props={src:'/one.png',imageWidth:999,imageHeight:777,classes:[{id:7,project_id:1,name:'Car'}],classId:7,
    annotations:[],mode:'draw' as const,onSelect:vi.fn(),onAdd:vi.fn(),onChange:vi.fn(),...overrides};
  const result=render(<AnnotationCanvas {...props}/>);
  const load=(w:number,h:number)=>{const img=result.container.querySelector('img')!;Object.defineProperties(img,{naturalWidth:{value:w,configurable:true},naturalHeight:{value:h,configurable:true}});fireEvent.load(img);};
  load(width,height);
  const region=screen.getByRole('region',{name:'Annotation workspace'});
  const view=():Viewport=>{
    const values=result.container.querySelector<HTMLElement>('.annotation-surface')!.style.transform.match(/-?\d*\.?\d+(?:e[+-]?\d+)?/g)!.map(Number);
    return {offsetX:values[0],offsetY:values[1],scale:values[2]};
  };
  const eventAt=(p:[number,number])=>{const [x,y]=imageToScreen(p,view());return {clientX:bounds.left+x,clientY:bounds.top+y,button:0};};
  const pan=()=>{fireEvent.keyDown(window,{code:'Space',key:' '});fireEvent.pointerDown(region,{clientX:200,clientY:200,button:0});fireEvent.pointerMove(region,{clientX:237,clientY:181});fireEvent.pointerUp(region,{clientX:237,clientY:181});fireEvent.keyUp(window,{code:'Space',key:' '});};
  const scaleTo=(scale:number)=>{
    fireEvent.click(screen.getByRole('button',{name:'Reset 100%'}));
    fireEvent.wheel(region,{deltaY:-Math.log(scale)/0.0015,clientX:bounds.left+400,clientY:bounds.top+250});
  };
  return {...result,props,region,view,eventAt,pan,scaleTo,load};
}
describe('annotation viewport',()=>{
  for(const [start,end] of [ [[120,110],[180,170]], [[180,110],[120,170]], [[120,170],[180,110]], [[180,170],[120,110]] ] as [number,number][][]) it(`draws a clamped box in drag direction ${start} to ${end}`,()=>{
    const s=setup();s.scaleTo(4);s.pan();
    fireEvent.pointerDown(s.container.querySelector('svg')!,s.eventAt(start));fireEvent.pointerMove(s.region,s.eventAt(end));fireEvent.pointerUp(s.region,s.eventAt(end));
    expect(s.props.onAdd).toHaveBeenCalledWith(expect.objectContaining({x:120,y:110,width:60,height:60}));
  });
  it('clamps a new box to the natural image and does not draw while space is held',()=>{
    const s=setup();s.scaleTo(2);s.pan();
    fireEvent.pointerDown(s.container.querySelector('svg')!,s.eventAt([120,110]));fireEvent.pointerMove(s.region,s.eventAt([-100,900]));fireEvent.pointerUp(s.region,s.eventAt([-100,900]));
    expect(s.props.onAdd).toHaveBeenCalledWith(expect.objectContaining({x:0,y:110,width:120,height:690}));
    vi.mocked(s.props.onAdd).mockClear();fireEvent.keyDown(window,{key:' ',code:'Space'});
    fireEvent.pointerDown(s.container.querySelector('svg')!,s.eventAt([120,110]));fireEvent.pointerMove(s.region,s.eventAt([160,170]));fireEvent.pointerUp(s.region,s.eventAt([160,170]));fireEvent.keyUp(window,{key:' ',code:'Space'});
    expect(s.props.onAdd).not.toHaveBeenCalled();
  });
  for(const scale of [1,2,4]) for(const mode of ['draw','polygon'] as const) it(`draws ${mode} at ${scale*100}% after pan in natural pixels`,()=>{
    const s=setup({mode});s.scaleTo(scale);s.pan();
    const svg=s.container.querySelector('svg')!;
    if(mode==='draw'){
      fireEvent.pointerDown(svg,s.eventAt([180.125,170.25]));
      fireEvent.pointerMove(s.region,s.eventAt([120.625,110.75]));
      fireEvent.pointerUp(s.region,s.eventAt([120.625,110.75]));
      expect(s.props.onAdd).toHaveBeenCalledWith(expect.objectContaining({x:120.625,y:110.75,width:59.5,height:59.5,points:null}));
    }else{
      for(const p of [[120.5,110.25],[170.5,110.25],[170.5,180.25]] as [number,number][])fireEvent.pointerDown(svg,s.eventAt(p));
      fireEvent.click(screen.getByRole('button',{name:'Finish polygon'}));
      expect(s.props.onAdd).toHaveBeenCalledWith(expect.objectContaining({points:[[120.5,110.25],[170.5,110.25],[170.5,180.25]],x:120.5,y:110.25}));
    }
    expect(s.view().scale).toBeCloseTo(scale);
    expect(s.props.onChange).not.toHaveBeenCalled();
  });
  it('zooms around the cursor, scopes wheel prevention and never mutates annotations',()=>{
    const s=setup();const before=s.view(),anchor:[number,number]=[240,180];
    const pixel:[number,number]=[(anchor[0]-before.offsetX)/before.scale,(anchor[1]-before.offsetY)/before.scale];
    const wheel=new WheelEvent('wheel',{clientX:bounds.left+240,clientY:bounds.top+180,deltaY:-100,bubbles:true,cancelable:true});
    act(()=>s.region.dispatchEvent(wheel));
    expect(wheel.defaultPrevented).toBe(true);
    const after=imageToScreen(pixel,s.view());expect(after[0]).toBeCloseTo(240);expect(after[1]).toBeCloseTo(180);
    const outside=new WheelEvent('wheel',{deltaY:100,bubbles:true,cancelable:true});document.body.dispatchEvent(outside);expect(outside.defaultPrevented).toBe(false);
    s.pan();fireEvent.click(screen.getByRole('button',{name:'Zoom in'}));fireEvent.click(screen.getByRole('button',{name:'Zoom out'}));
    expect(s.props.onChange).not.toHaveBeenCalled();expect(s.props.onAdd).not.toHaveBeenCalled();
  });
  it('moves and resizes existing boxes, preserving ID and permissions after zoom and pan',()=>{
    const item={id:9,class_id:7,class_name:'Car',annotation_type:'bbox' as const,x:120,y:110,width:80,height:70,can_edit:true};
    const s=setup({annotations:[item],selected:9,mode:'select'});s.scaleTo(4);s.pan();
    const object=s.container.querySelector('[data-annotation-id]')!;
    fireEvent.pointerDown(object,s.eventAt([125,115]));fireEvent.pointerMove(s.region,s.eventAt([135.25,130.5]));fireEvent.pointerUp(s.region);
    expect(s.props.onChange).toHaveBeenLastCalledWith(9,{x:130.25,y:125.5});
    fireEvent.pointerDown(screen.getByLabelText('Resize se'),s.eventAt([200,180]));fireEvent.pointerMove(s.region,s.eventAt([220,210]));fireEvent.pointerUp(s.region);
    expect(s.props.onChange).toHaveBeenLastCalledWith(9,{x:120,y:110,width:100,height:100});
    s.rerender(<AnnotationCanvas {...s.props} annotations={[{...item,can_edit:false}]}/>);
    expect(screen.queryByLabelText('Resize se')).toBeNull();vi.mocked(s.props.onChange).mockClear();
    fireEvent.pointerDown(object,s.eventAt([125,115]));fireEvent.pointerMove(s.region,s.eventAt([145,135]));fireEvent.pointerUp(s.region);
    expect(s.props.onChange).not.toHaveBeenCalled();
  });
  it('edits polygon vertices with natural bounds and keeps AI geometry in the same surface',()=>{
    const item={id:9,class_id:7,class_name:'Car',annotation_type:'polygon' as const,x:120,y:110,width:80,height:70,points:[[120,110],[200,110],[200,180]] as [number,number][],can_edit:true};
    const prediction={id:2,image_id:1,model_class_id:0,model_class_name:'Car',mapped_class_id:7,mapped_class_name:'Car',prediction_type:'polygon' as const,x:120,y:110,width:80,height:70,points:item.points,confidence:0.9,status:'PENDING' as const};
    const s=setup({annotations:[item],predictions:[prediction],selected:9,mode:'select'});s.scaleTo(2);s.pan();
    fireEvent.pointerDown(screen.getByLabelText('Vertex 1'),s.eventAt([120,110]));fireEvent.pointerMove(s.region,s.eventAt([-20,900]));fireEvent.pointerUp(s.region);
    expect(s.props.onChange).toHaveBeenLastCalledWith(9,expect.objectContaining({points:[[0,800],[200,110],[200,180]]}));
    expect(s.container.querySelectorAll('.annotation-surface polygon')).toHaveLength(2);
  });
  it('pans over objects without selecting, drawing, editing or deleting',()=>{
    const s=setup({mode:'select',selected:9,annotations:[{id:9,class_id:7,class_name:'Car',annotation_type:'bbox',x:120,y:110,width:80,height:70,can_edit:true}]});
    const before=s.view();fireEvent.keyDown(window,{code:'Space',key:' '});
    fireEvent.pointerDown(s.container.querySelector('[data-annotation-id]')!,s.eventAt([125,115]));
    fireEvent.pointerMove(s.region,{clientX:300,clientY:300});
    const deletion=new KeyboardEvent('keydown',{key:'Delete',cancelable:true});window.dispatchEvent(deletion);expect(deletion.defaultPrevented).toBe(true);
    fireEvent.pointerUp(s.region);fireEvent.keyUp(window,{code:'Space',key:' '});
    expect(s.view()).not.toEqual(before);expect(s.props.onSelect).not.toHaveBeenCalled();expect(s.props.onChange).not.toHaveBeenCalled();expect(s.props.onAdd).not.toHaveBeenCalled();
  });
  it('fits, resets to native pixels, handles resize and discards old image dimensions',()=>{
    const s=setup({},100000,80000);expect(s.view().scale).toBe(0.00625);
    fireEvent.click(screen.getByRole('button',{name:'Reset 100%'}));expect(s.view().scale).toBe(1);
    fireEvent.click(screen.getByRole('button',{name:'Fit to screen'}));bounds={...bounds,width:400,height:300};fireEvent(window,new Event('resize'));expect(s.view().scale).toBe(0.00375);
    fireEvent.click(screen.getByRole('button',{name:'Reset 100%'}));const before=s.view();bounds={...bounds,width:600,height:400};fireEvent(window,new Event('resize'));expect(s.view()).toEqual({...before,offsetX:before.offsetX+100,offsetY:before.offsetY+50});
    s.rerender(<AnnotationCanvas {...s.props} src='/two.png'/>);expect(s.container.querySelector('svg')).toBeNull();
    s.load(100,50);expect(s.view()).toEqual({scale:6,offsetX:0,offsetY:50});expect(s.container.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 100 50');
  });
  it('allows read-only users to inspect using zoom and pan without editing',()=>{
    const s=setup({readOnly:true});s.scaleTo(4);s.pan();
    fireEvent.pointerDown(s.container.querySelector('svg')!,s.eventAt([120,110]));fireEvent.pointerMove(s.region,s.eventAt([160,170]));fireEvent.pointerUp(s.region,s.eventAt([160,170]));
    expect(s.props.onAdd).not.toHaveBeenCalled();expect(s.props.onChange).not.toHaveBeenCalled();expect(s.view().scale).toBe(4);
  });
});
