// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import EditorPage from './EditorPage';
import {api} from '../services/api';
import type {Annotation} from '../types';

vi.mock('../services/api',()=>({api:{get:vi.fn(),put:vi.fn()},imageUrl:(url:string)=>url}));
vi.mock('../workspaces/WorkspaceProvider',()=>({useWorkspace:()=>({current:{id:1}})}));
vi.mock('../components/ProtectedImage',()=>({default:({onLoadFailure,...props}:any)=><img {...props}/>}));
vi.mock('../components/AutoLabelPanel',()=>({default:()=>null}));
const original:Annotation={id:9,image_id:1,class_id:7,class_name:'Car',annotation_type:'bbox',x:120,y:110,width:80,height:70,
  points:null,version:3,can_edit:true,can_delete:true,created_by:{id:'a',full_name:'Creator'}};
let stored:Annotation[];
beforeEach(()=>{
  stored=[{...original}];vi.clearAllMocks();vi.stubGlobal('PointerEvent',MouseEvent);vi.stubGlobal('alert',vi.fn());
  vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){return (this.classList.contains('annotation-viewport')?{left:70,top:120,width:800,height:500}:{left:0,top:0,width:0,height:0}) as DOMRect;});
  vi.mocked(api.get).mockImplementation(async(url)=>({data: url==='/projects/1'?{id:1,workspace_id:1,annotation_mode:'object_detection',permissions:['annotation.update','annotation.delete']}:
    url==='/images/1'?{id:1,project_id:1,filename:'one.png',width:1000,height:800,image_url:'/one.png'}:
    url==='/images/1/annotations'?stored:url==='/projects/1/classes'?[{id:7,project_id:1,name:'Car'}]:[{id:1}]}));
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
async function openEditor(){
  const result=render(<MemoryRouter initialEntries={['/projects/1/images/1']}><Routes><Route path='/projects/:projectId/images/:imageId' element={<EditorPage/>}/></Routes></MemoryRouter>);
  const img=await screen.findByAltText('Annotation target');Object.defineProperties(img,{naturalWidth:{value:1000},naturalHeight:{value:800}});fireEvent.load(img);
  await waitFor(()=>expect(result.container.querySelector('[data-annotation-id="9"]')).toBeTruthy());
  return result;
}
it('retains viewport/drafts on failed save and resets only after successful API confirmation; reload retains pixel geometry',async()=>{
  const result=await openEditor(),region=screen.getByRole('region',{name:'Annotation workspace'});
  fireEvent.click(screen.getByRole('button',{name:'Reset 100%'}));fireEvent.wheel(region,{deltaY:-Math.log(4)/0.0015,clientX:470,clientY:370});
  fireEvent.keyDown(window,{key:' ',code:'Space'});fireEvent.pointerDown(region,{clientX:200,clientY:200,button:0});fireEvent.pointerMove(region,{clientX:237,clientY:181});fireEvent.pointerUp(region);fireEvent.keyUp(window,{key:' ',code:'Space'});
  const surface=result.container.querySelector<HTMLElement>('.annotation-surface')!,before=surface.style.transform;
  const [ox,oy,scale]=before.match(/-?\d*\.?\d+/g)!.map(Number);
  const pointer=(x:number,y:number)=>({clientX:70+ox+x*scale,clientY:120+oy+y*scale,button:0});
  fireEvent.pointerDown(result.container.querySelector('[data-annotation-id="9"]')!,pointer(125,115));fireEvent.pointerMove(region,pointer(132.5,126.25));fireEvent.pointerUp(region);
  vi.mocked(api.put).mockRejectedValueOnce({response:{data:{detail:'Version conflict'}}});
  fireEvent.click(screen.getByRole('button',{name:'Save draft'}));await screen.findByText('Version conflict');
  expect(surface.style.transform).toBe(before);expect(result.container.querySelector('[data-annotation-id="9"]>rect')?.getAttribute('x')).toBe('127.5');
  let finish!:(value:any)=>void;
  vi.mocked(api.put).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  fireEvent.click(screen.getByRole('button',{name:'Save draft'}));await screen.findByRole('button',{name:'Saving…'});
  expect(surface.style.transform).toBe(before);
  expect(api.put).toHaveBeenLastCalledWith('/images/1/annotations',expect.objectContaining({expected_versions:{9:3},items:[expect.objectContaining({id:9,x:127.5,y:121.25,width:80,height:70})]}));
  stored=[{...original,x:127.5,y:121.25,version:4,updated_by:{id:'b',full_name:'Editor'}}];
  await act(async()=>{finish({data:stored});});
  await waitFor(()=>expect(screen.getByLabelText('Zoom level').textContent).toBe('100%'));
  expect(surface.style.transform).toBe('translate(-100px, -150px) scale(1)');
  expect(result.container.querySelector('[data-annotation-id="9"]>rect')?.getAttribute('x')).toBe('127.5');
  expect(result.container.querySelector('title')?.textContent).toContain('Creator');
  result.unmount();const reloaded=await openEditor();
  expect(reloaded.container.querySelector('[data-annotation-id="9"]>rect')?.getAttribute('x')).toBe('127.5');
  expect(reloaded.container.querySelector('[data-annotation-id="9"]>rect')?.getAttribute('y')).toBe('121.25');
});
