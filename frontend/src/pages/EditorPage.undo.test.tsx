// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import EditorPage from './EditorPage';
import {api} from '../services/api';
import type {Annotation,Prediction} from '../types';

vi.mock('../services/api',()=>({api:{get:vi.fn(),put:vi.fn(),post:vi.fn(),delete:vi.fn()},imageUrl:(url:string)=>url}));
vi.mock('../workspaces/WorkspaceProvider',()=>({useWorkspace:()=>({current:{id:'ws'}})}));
vi.mock('../quality/useAnnotationActivity',()=>({useAnnotationActivity:vi.fn()}));
vi.mock('../components/ProtectedImage',()=>({default:({onLoadFailure,...props}:any)=><img {...props}/>}));
const original:Annotation={id:99,image_id:1,class_id:7,class_name:'Car',annotation_type:'bbox',x:120,y:110,width:80,height:70,points:null,version:3,can_edit:true,can_delete:true,created_by:{id:'author',full_name:'Original author'},source:'manual'};
const suggestions:Prediction[]=[1,2].map(id=>({id,image_id:1,model_class_id:0,model_class_name:'car',mapped_class_id:7,mapped_class_name:'Car',prediction_type:'bbox',x:400,y:300,width:50,height:50,confidence:.9,status:'PENDING',draft_token:`token-${id}`}));
let mode='object_detection',stored:Annotation[],predictions:Prediction[];
beforeEach(()=>{
 mode='object_detection';stored=structuredClone([original]);predictions=structuredClone(suggestions);vi.clearAllMocks();
 vi.stubGlobal('PointerEvent',MouseEvent);vi.spyOn(window,'confirm').mockReturnValue(true);
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){return (this.classList.contains('annotation-viewport')?{left:70,top:120,width:800,height:500}:{left:0,top:0,width:0,height:0}) as DOMRect;});
 vi.mocked(api.get).mockImplementation(async url=>({data:url==='/projects/1'?{id:1,workspace_id:'ws',annotation_mode:mode,permissions:['annotation.create','annotation.update','annotation.delete','prediction.run','prediction.review']}:
   /^\/images\/\d+$/.test(String(url))?{id:Number(String(url).split('/').pop()),project_id:1,filename:'one.png',width:1000,height:800,image_url:'/one.png'}:
   String(url).endsWith('/annotations')?stored:String(url).endsWith('/predictions')?predictions:
   String(url).endsWith('/review')?{}:String(url).endsWith('/classes')?[{id:7,name:'Car'},{id:8,name:'Bus'}]:[{id:1},{id:2}]}));
 vi.mocked(api.put).mockImplementation(async(_url,data:any)=>({data:data.items.map((a:any,i:number)=>({...a,id:a.id??i+200,image_id:1,class_name:'Car',version:4,can_edit:true,can_delete:true,created_by:original.created_by}))}));
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
async function open(){
 const result=render(<MemoryRouter initialEntries={['/projects/1/images/1']}><Routes><Route path='/projects/:projectId/images/:imageId' element={<EditorPage/>}/></Routes></MemoryRouter>);
 const img=await screen.findByAltText('Annotation target');Object.defineProperties(img,{naturalWidth:{value:1000},naturalHeight:{value:800}});fireEvent.load(img);
 await waitFor(()=>expect(result.container.querySelector('svg')).toBeTruthy());return result;
}
const undo=()=>screen.getByRole<HTMLButtonElement>('button',{name:'Undo'});
const objects=(container:HTMLElement)=>container.querySelectorAll('.quality-object-list > button');
function point(container:HTMLElement,x:number,y:number){
 const [ox,oy,scale]=container.querySelector<HTMLElement>('.annotation-surface')!.style.transform.match(/-?\d*\.?\d+/g)!.map(Number);
 return {clientX:70+ox+x*scale,clientY:120+oy+y*scale,button:0};
}

it('undoes a creation, multi-move gesture, resize and delete as distinct steps without changing zoom',async()=>{
 const {container}=await open(),region=screen.getByRole('region',{name:'Annotation workspace'});
 fireEvent.click(screen.getByRole('button',{name:'Zoom in'}));expect(undo().disabled).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'● Car'}));fireEvent.click(screen.getByRole('button',{name:'Bounding Box'}));
 fireEvent.pointerDown(container.querySelector('svg')!,point(container,500,400));fireEvent.pointerMove(region,point(container,550,450));fireEvent.pointerUp(region,point(container,550,450));
 const created=container.querySelector('[data-annotation-id="-1"]')!;expect(created).toBeTruthy();
 fireEvent.pointerDown(created,point(container,510,410));
 for(let x=511;x<=530;x++)fireEvent.pointerMove(region,point(container,x,410));
 fireEvent.pointerUp(region,point(container,530,410));
 fireEvent.pointerDown(screen.getByLabelText('Resize se'),point(container,570,450));fireEvent.pointerMove(region,point(container,590,480));fireEvent.pointerUp(region,point(container,590,480));
 fireEvent.click(screen.getByRole('button',{name:'Delete'}));expect(objects(container)).toHaveLength(1);
 const transform=container.querySelector<HTMLElement>('.annotation-surface')!.style.transform;
 fireEvent.click(undo());expect(container.querySelector('[data-annotation-id="-1"] > rect')?.getAttribute('width')).toBe('70');
 fireEvent.click(undo());expect(container.querySelector('[data-annotation-id="-1"] > rect')?.getAttribute('width')).toBe('50');
 fireEvent.click(undo());expect(container.querySelector('[data-annotation-id="-1"] > rect')?.getAttribute('x')).toBe('500');
 fireEvent.click(undo());expect(objects(container)).toHaveLength(1);expect(undo().disabled).toBe(true);
 expect(container.querySelector<HTMLElement>('.annotation-surface')!.style.transform).toBe(transform);expect(api.put).not.toHaveBeenCalled();
});

it('undoes polygon draft points first, then the completed polygon as one operation',async()=>{
 mode='instance_segmentation';stored=[];
 const {container}=await open();fireEvent.click(screen.getByRole('button',{name:'● Car'}));fireEvent.click(screen.getByRole('button',{name:'Polygon'}));
 const svg=container.querySelector('svg')!;
 fireEvent.pointerDown(svg,point(container,100,100));fireEvent.pointerDown(svg,point(container,200,100));
 fireEvent.keyDown(window,{key:'z',ctrlKey:true});expect(container.querySelector('polyline')?.getAttribute('points')).toBe('100,100');
 fireEvent.click(undo());expect(container.querySelector('polyline')).toBeNull();expect(undo().disabled).toBe(true);
 for(const [x,y] of [[100,100],[200,100],[200,200]])fireEvent.pointerDown(svg,point(container,x,y));
 fireEvent.click(screen.getByRole('button',{name:'Finish polygon'}));expect(objects(container)).toHaveLength(1);
 fireEvent.keyDown(window,{key:'z',metaKey:true});expect(objects(container)).toHaveLength(0);expect(container.querySelector('polyline')).toBeNull();expect(undo().disabled).toBe(true);
});

it('keeps native text undo, undoes class changes, and restores Delete All with IDs and authors intact',async()=>{
 const {container}=await open();fireEvent.click(container.querySelector('#annotation-object-99')!);
 fireEvent.change(screen.getByRole('combobox',{name:'Object class'}),{target:{value:'8'}});expect(undo().disabled).toBe(false);
 for(const tag of ['input','textarea','div']){
   const input=document.createElement(tag);if(tag==='div'){input.contentEditable='true';input.setAttribute('contenteditable','');}
   document.body.append(input);const event=new KeyboardEvent('keydown',{key:'z',ctrlKey:true,bubbles:true,cancelable:true});input.dispatchEvent(event);
   expect(event.defaultPrevented).toBe(false);expect(container.querySelector('#annotation-object-99')?.textContent).toContain('Bus');input.remove();
 }
 fireEvent.keyDown(window,{key:'z',ctrlKey:true});expect(container.querySelector('#annotation-object-99')?.textContent).toContain('Car');expect(undo().disabled).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Delete All Labels'}));expect(objects(container)).toHaveLength(0);expect(api.delete).not.toHaveBeenCalled();
 fireEvent.click(undo());expect(container.querySelector('#annotation-object-99')?.textContent).toContain('Original author');expect(undo().disabled).toBe(true);
});

it('stages AI acceptance as one undo step, restores proposals after Undo, and saves with the prediction tokens',async()=>{
 const {container}=await open();await screen.findAllByText('car · 90% → Car');
 fireEvent.click(screen.getByRole('button',{name:'Accept All'}));expect(objects(container)).toHaveLength(3);expect(container.querySelectorAll('.prediction-list button')).toHaveLength(0);
 expect(api.post).not.toHaveBeenCalled();expect(api.put).not.toHaveBeenCalled();
 fireEvent.click(undo());expect(objects(container)).toHaveLength(1);expect(container.querySelectorAll('.prediction-list button')).toHaveLength(2);expect(undo().disabled).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Accept All'}));
 vi.mocked(api.put).mockRejectedValueOnce({response:{data:{detail:'Version conflict'}}});fireEvent.click(screen.getByRole('button',{name:'Save draft'}));await screen.findByText('Version conflict');expect(undo().disabled).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Save draft'}));await screen.findByText('Draft saved. It has not been submitted for review.');expect(undo().disabled).toBe(true);
 expect(vi.mocked(api.put).mock.calls[1][1]).toMatchObject({expected_versions:{99:3},items:[{id:99},{prediction_id:1,prediction_token:'token-1'},{prediction_id:2,prediction_token:'token-2'}]});
});

it('clears history and polygon points on image navigation',async()=>{
 const {container}=await open();fireEvent.click(screen.getByRole('button',{name:'Delete All Labels'}));expect(undo().disabled).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Next ›'}));await waitFor(()=>expect(objects(container)).toHaveLength(1));expect(undo().disabled).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'‹ Previous'}));await waitFor(()=>expect(objects(container)).toHaveLength(1));expect(undo().disabled).toBe(true);
});

it('undoes a multi-move polygon vertex edit in one step',async()=>{
 mode='instance_segmentation';stored=[{...original,annotation_type:'polygon',points:[[120,110],[200,110],[200,180]]}];
 const {container}=await open(),region=screen.getByRole('region',{name:'Annotation workspace'});
 fireEvent.click(container.querySelector('#annotation-object-99')!);
 fireEvent.pointerDown(screen.getByLabelText('Vertex 1'),point(container,120,110));
 for(let x=121;x<=140;x++)fireEvent.pointerMove(region,point(container,x,115));
 fireEvent.pointerUp(region,point(container,140,115));
 expect(container.querySelector('[data-annotation-id="99"] > polygon')?.getAttribute('points')).toBe('140,115 200,110 200,180');
 fireEvent.click(undo());expect(container.querySelector('[data-annotation-id="99"] > polygon')?.getAttribute('points')).toBe('120,110 200,110 200,180');expect(undo().disabled).toBe(true);
});
