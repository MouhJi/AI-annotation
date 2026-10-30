// @vitest-environment jsdom
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import AnnotationAttribution,{annotationLabel} from './AnnotationAttribution';
import AnnotationCanvas from './AnnotationCanvas';
import type {DraftAnnotation} from '../types';
vi.mock('./ProtectedImage',()=>({default:({onLoadFailure,...props}:any)=><img {...props}/>}));
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
const item:DraftAnnotation={id:1,class_id:1,class_name:'Car',annotation_type:'bbox',x:0,y:0,width:40,height:30,created_by:{id:'a',full_name:'Nguyễn An'},updated_by:{id:'b',full_name:'Trần Bình'},source:'ai_accepted',created_at:'2026-10-22T10:00:00Z'};
describe('object attribution',()=>{
 it('shows full creator and last editor in details',()=>{render(<AnnotationAttribution annotation={item}/>);expect(screen.getByText('Created by: Nguyễn An')).toBeTruthy();expect(screen.getByText('Last edited by: Trần Bình')).toBeTruthy();expect(screen.getByText('Source: AI (YOLO)')).toBeTruthy()});
 it('distinguishes human refinement of AI objects from unknown legacy sources',()=>{const view=render(<AnnotationAttribution annotation={{...item,source:'ai_edited'}}/>);expect(screen.getByText('Source: AI with human edits')).toBeTruthy();view.rerender(<AnnotationAttribution annotation={{...item,source:'legacy'}}/>);expect(screen.getByText('Source: Unknown')).toBeTruthy()});
 it('distinguishes legacy and unsaved objects',()=>{expect(annotationLabel({...item,created_by:null})).toBe('Car · Unknown annotator');expect(annotationLabel({...item,isNew:true})).toBe('Car · Unsaved')});
 for(const type of ['bbox','polygon'] as const) it(`renders ${type} author, clamps edge label and keeps selection`,()=>{
   const onSelect=vi.fn();const {container}=render(<AnnotationCanvas src='/image.png' imageWidth={100} imageHeight={80} classes={[{id:1,project_id:1,name:'Car'}]} annotations={[{...item,annotation_type:type,points:[[0,0],[40,0],[40,30]]}]} mode='select' readOnly selected={1} onSelect={onSelect} onAdd={vi.fn()} onChange={vi.fn()}/>);
   const img=container.querySelector('img')!;Object.defineProperty(img,'naturalWidth',{value:100});Object.defineProperty(img,'naturalHeight',{value:80});fireEvent.load(img);
   expect(container.querySelector('title')?.textContent).toBe('Car · Nguyễn An');const label=container.querySelector('text')!;expect(Number(label.getAttribute('y'))).toBeGreaterThan(0);expect(label.parentElement?.getAttribute('pointer-events')).toBe('none');fireEvent.mouseDown(container.querySelector(type==='bbox'?'rect':'polygon')!);expect(onSelect).toHaveBeenCalledWith(1);
 });
 it('retains long Unicode names in details',()=>{const name='Nguyễn Thị '.repeat(50);render(<AnnotationAttribution annotation={{...item,created_by:{id:'a',full_name:name}}}/>);expect(screen.getByLabelText('Object details').textContent).toContain(name)});
});
it('drags/resizes existing bbox and vertex without adding new objects',()=>{
 vi.stubGlobal('PointerEvent',MouseEvent);
 const change=vi.fn(),add=vi.fn();const {container}=render(<AnnotationCanvas src='/image.png' imageWidth={100} imageHeight={80} classes={[]} annotations={[{...item,can_edit:true}]} mode='select' selected={1} onSelect={vi.fn()} onAdd={add} onChange={change}/>);
 const img=container.querySelector('img')!;Object.defineProperty(img,'naturalWidth',{value:100});Object.defineProperty(img,'naturalHeight',{value:80});fireEvent.load(img);
 const svg=container.querySelector('svg')!;vi.spyOn(svg,'getBoundingClientRect').mockReturnValue({left:0,top:0,width:100,height:80} as DOMRect);
 fireEvent.pointerDown(container.querySelector('[data-annotation-id]')!,{clientX:5,clientY:5,button:0});
 fireEvent.pointerMove(svg,{clientX:15,clientY:15});fireEvent.pointerUp(svg);
 expect(change).toHaveBeenCalledWith(1,{x:10,y:10});expect(add).not.toHaveBeenCalled();
 fireEvent.pointerDown(container.querySelector('[aria-label="Resize se"]')!,{clientX:40,clientY:30,button:0});fireEvent.pointerMove(svg,{clientX:50,clientY:40});fireEvent.pointerUp(svg);
 expect(change).toHaveBeenLastCalledWith(1,{x:0,y:0,width:50,height:40});
});
it('hides handles for objects without correction permission',()=>{
 const {container}=render(<AnnotationCanvas src='/image.png' imageWidth={100} imageHeight={80} classes={[]} annotations={[{...item,can_edit:false}]} mode='select' selected={1} onSelect={vi.fn()} onAdd={vi.fn()} onChange={vi.fn()}/>);
 const img=container.querySelector('img')!;Object.defineProperty(img,'naturalWidth',{value:100});Object.defineProperty(img,'naturalHeight',{value:80});fireEvent.load(img);expect(container.querySelector('[aria-label^="Resize"]')).toBeNull();
});
it('edits an existing polygon vertex using pointer capture and preserves its ID',()=>{
 vi.stubGlobal('PointerEvent',MouseEvent);const change=vi.fn(),add=vi.fn();
 const {container}=render(<AnnotationCanvas src='/image.png' imageWidth={100} imageHeight={80} classes={[]} annotations={[{...item,can_edit:true,annotation_type:'polygon',points:[[5,5],[40,5],[40,30],[5,30]]}]} mode='select' selected={1} onSelect={vi.fn()} onAdd={add} onChange={change}/>);
 const img=container.querySelector('img')!;Object.defineProperty(img,'naturalWidth',{value:100});Object.defineProperty(img,'naturalHeight',{value:80});fireEvent.load(img);
 const svg=container.querySelector('svg')!;vi.spyOn(svg,'getBoundingClientRect').mockReturnValue({left:0,top:0,width:100,height:80} as DOMRect);
 fireEvent.pointerDown(container.querySelector('[aria-label="Vertex 1"]')!,{clientX:5,clientY:5,button:0});fireEvent.pointerMove(svg,{clientX:10,clientY:10});fireEvent.pointerUp(svg);
 expect(change.mock.calls[0][0]).toBe(1);expect(change.mock.calls[0][1].points[0]).toEqual([10,10]);expect(change.mock.calls[0][1].points[1]).toEqual([40,5]);expect(add).not.toHaveBeenCalled();
});
