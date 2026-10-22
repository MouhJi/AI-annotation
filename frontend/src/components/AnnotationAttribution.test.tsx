// @vitest-environment jsdom
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import AnnotationAttribution,{annotationLabel} from './AnnotationAttribution';
import AnnotationCanvas from './AnnotationCanvas';
import type {DraftAnnotation} from '../types';
vi.mock('./ProtectedImage',()=>({default:(props:any)=><img {...props}/>}));
afterEach(cleanup);
const item:DraftAnnotation={id:1,class_id:1,class_name:'Car',annotation_type:'bbox',x:0,y:0,width:40,height:30,created_by:{id:'a',full_name:'Nguyễn An'},updated_by:{id:'b',full_name:'Trần Bình'},source:'ai_accepted',created_at:'2026-10-22T10:00:00Z'};
describe('object attribution',()=>{
 it('shows full creator and last editor in details',()=>{render(<AnnotationAttribution annotation={item}/>);expect(screen.getByText('Created by: Nguyễn An')).toBeTruthy();expect(screen.getByText('Last edited by: Trần Bình')).toBeTruthy();expect(screen.getByText('Source: AI-assisted (YOLO)')).toBeTruthy()});
 it('distinguishes legacy and unsaved objects',()=>{expect(annotationLabel({...item,created_by:null})).toBe('Car · Unknown annotator');expect(annotationLabel({...item,isNew:true})).toBe('Car · Unsaved')});
 for(const type of ['bbox','polygon'] as const) it(`renders ${type} author, clamps edge label and keeps selection`,()=>{
   const onSelect=vi.fn();const {container}=render(<AnnotationCanvas src='/image.png' imageWidth={100} imageHeight={80} classes={[{id:1,project_id:1,name:'Car'}]} annotations={[{...item,annotation_type:type,points:[[0,0],[40,0],[40,30]]}]} mode='select' readOnly selected={1} onSelect={onSelect} onAdd={vi.fn()} onChange={vi.fn()}/>);
   const img=container.querySelector('img')!;Object.defineProperty(img,'naturalWidth',{value:100});Object.defineProperty(img,'naturalHeight',{value:80});fireEvent.load(img);
   expect(container.querySelector('title')?.textContent).toBe('Car · Nguyễn An');const label=container.querySelector('text')!;expect(Number(label.getAttribute('y'))).toBeGreaterThan(0);expect(label.parentElement?.getAttribute('pointer-events')).toBe('none');fireEvent.mouseDown(container.querySelector(type==='bbox'?'rect':'polygon')!);expect(onSelect).toHaveBeenCalledWith(1);
 });
 it('retains long Unicode names in details',()=>{const name='Nguyễn Thị '.repeat(50);render(<AnnotationAttribution annotation={{...item,created_by:{id:'a',full_name:name}}}/>);expect(screen.getByLabelText('Object details').textContent).toContain(name)});
});
