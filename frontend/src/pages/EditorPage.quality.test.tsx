// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import EditorPage from './EditorPage';
import {api} from '../services/api';
import type {Annotation,ReviewDetail} from '../types';
vi.mock('../services/api',()=>({api:{get:vi.fn(),put:vi.fn(),post:vi.fn()},imageUrl:(url:string)=>url}));
vi.mock('../workspaces/WorkspaceProvider',()=>({useWorkspace:()=>({current:{id:'ws'}})}));
vi.mock('../quality/useAnnotationActivity',()=>({useAnnotationActivity:vi.fn()}));
vi.mock('../components/ProtectedImage',()=>({default:({onLoadFailure,...props}:any)=><img {...props}/>}));
vi.mock('../components/AutoLabelPanel',()=>({default:()=>null}));
const annotation:Annotation={id:99,image_id:1,class_id:7,class_name:'Car',annotation_type:'bbox',x:120,y:110,width:80,height:70,points:null,version:3,can_edit:true,can_delete:true,created_by:{id:'a',full_name:'Creator'}};
let review:ReviewDetail;
let displayedAnnotation:Annotation;
beforeEach(()=>{
  vi.clearAllMocks();vi.stubGlobal('PointerEvent',MouseEvent);
  displayedAnnotation={...annotation};
  review={state:'in_progress',revision:3,review_version:4,approved_revision:null,negative_confirmed:false,snapshot_id:3,contributors:[{id:'a',full_name:'Creator'}],can_approve:false,can_withdraw:false,independent_review_required:true,open_threads:1,idle_seconds:60,history:[]};
  vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){return (this.classList.contains('annotation-viewport')?{left:70,top:120,width:800,height:500}:{left:0,top:0,width:0,height:0}) as DOMRect;});
  vi.mocked(api.get).mockImplementation(async url=>({data:url==='/projects/1'?{id:1,workspace_id:'ws',annotation_mode:'object_detection',permissions:['annotation.update','annotation.delete','review.submit','review.read','comment.read']}:
    url==='/images/1'?{id:1,project_id:1,filename:'one.png',width:1000,height:800,image_url:'/one.png'}:
    url==='/images/1/annotations'?[displayedAnnotation]:url==='/images/1/review'?review:url==='/images/1/threads'?[{id:1,object_id:99,object_deleted:false,resolved:false,version:1,can_resolve:false,comments:[]}]:url==='/projects/1/classes'?[{id:7,project_id:1,name:'Car'}]:[{id:1}]}));
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
async function open(){
  const result=render(<MemoryRouter initialEntries={['/projects/1/images/1']}><Routes><Route path="/projects/:projectId/images/:imageId" element={<EditorPage/>}/></Routes></MemoryRouter>);
  const image=await screen.findByAltText('Annotation target');Object.defineProperties(image,{naturalWidth:{value:1000},naturalHeight:{value:800}});fireEvent.load(image);
  await waitFor(()=>expect(result.container.querySelector('[data-annotation-id="99"]')).toBeTruthy());return result;
}
it.each(['bbox','polygon'] as const)('selects a commented %s by stable ID after zoom/pan without changing the viewport or geometry',async type=>{
  displayedAnnotation={...annotation,annotation_type:type,points:type==='polygon'?[[120,110],[200,110],[200,180],[120,180]]:null};
  const result=await open(),region=screen.getByRole('region',{name:'Annotation workspace'});
  fireEvent.click(screen.getByRole('button',{name:'Reset 100%'}));fireEvent.wheel(region,{deltaY:-Math.log(4)/0.0015,clientX:470,clientY:370});
  fireEvent.keyDown(window,{key:' ',code:'Space'});fireEvent.pointerDown(region,{clientX:200,clientY:200,button:0});fireEvent.pointerMove(region,{clientX:245,clientY:180});fireEvent.pointerUp(region);fireEvent.keyUp(window,{key:' ',code:'Space'});
  const surface=result.container.querySelector<HTMLElement>('.annotation-surface')!,before=surface.style.transform;
  fireEvent.click(screen.getByRole('button',{name:'Discussions (1)'}));fireEvent.click(await screen.findByRole('button',{name:'Select object #99'}));
  expect(result.container.querySelector('#annotation-object-99')?.classList.contains('active')).toBe(true);
  expect(surface.style.transform).toBe(before);
  if(type==='bbox')expect(result.container.querySelector('[data-annotation-id="99"]>rect')?.getAttribute('x')).toBe('120');
  else expect(result.container.querySelector('[data-annotation-id="99"]>polygon')?.getAttribute('points')).toBe('120,110 200,110 200,180 120,180');
  expect(api.put).not.toHaveBeenCalled();expect(api.post).not.toHaveBeenCalled();
});
it('submits saved pixel coordinates atomically, keeps viewport on failure and locks editing only on success',async()=>{
  const result=await open(),region=screen.getByRole('region',{name:'Annotation workspace'});
  fireEvent.click(screen.getByRole('button',{name:'Reset 100%'}));fireEvent.wheel(region,{deltaY:-Math.log(2)/0.0015,clientX:470,clientY:370});
  const surface=result.container.querySelector<HTMLElement>('.annotation-surface')!,before=surface.style.transform;
  fireEvent.click(screen.getByRole('button',{name:'Image review'}));vi.mocked(api.post).mockRejectedValueOnce({response:{data:{detail:'Revision conflict. Reload.'}}});
  fireEvent.click(screen.getByRole('button',{name:'Submit for review'}));await screen.findByText('Revision conflict. Reload.');expect(surface.style.transform).toBe(before);
  expect(screen.getByRole('button',{name:'Save draft'})).toBeTruthy();
  let finish!:(value:any)=>void;vi.mocked(api.post).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));fireEvent.click(screen.getByRole('button',{name:'Submit for review'}));
  expect(api.post).toHaveBeenLastCalledWith('/images/1/review/submit',{expected_revision:3,expected_review_version:4,negative_confirmed:false,annotations:expect.objectContaining({expected_revision:3,expected_versions:{99:3},items:[expect.objectContaining({id:99,x:120,y:110,width:80,height:70})]})});
  review={...review,state:'pending_review',review_version:5,can_withdraw:true};await act(async()=>finish({data:{review,annotations:[{...annotation,can_edit:false,can_delete:false}]}}));
  await waitFor(()=>expect(screen.getByLabelText('Zoom level').textContent).toBe('100%'));
  expect(screen.queryByRole('button',{name:'Save draft'})).toBeNull();expect(screen.queryByRole('button',{name:'Delete All Labels'})).toBeNull();
  expect(screen.getByText('Editing locked')).toBeTruthy();expect(result.container.querySelector('[data-annotation-id="99"]>rect')?.getAttribute('x')).toBe('120');
});
