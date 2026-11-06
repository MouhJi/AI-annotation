// @vitest-environment jsdom
import {renderHook,act,waitFor,cleanup} from '@testing-library/react';
import {it,expect,vi,afterEach} from 'vitest';
import {useAnnotations} from './useAnnotations';
import {api} from '../services/api';
import type {Annotation,Prediction} from '../types';
vi.mock('../services/api',()=>({api:{put:vi.fn(),post:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks()});
const initial:Annotation[]=[{id:1,image_id:2,class_id:3,class_name:'Car',annotation_type:'bbox',x:1,y:1,width:20,height:20,version:1,can_edit:true,can_delete:true,created_by:{id:'a',full_name:'Nguyễn An'}}];
it('saves one atomic diff with versions and adopts returned metadata',async()=>{
 const saved={...initial[0],width:25,version:2,updated_by:{id:'b',full_name:'Trần Bình'}};
 vi.mocked(api.put).mockResolvedValue({data:[saved]});
 const {result}=renderHook(()=>useAnnotations(2,initial));act(()=>result.current.update(1,{width:25}));
 await act(async()=>{await result.current.save()});
 expect(api.put).toHaveBeenCalledTimes(1);const payload=vi.mocked(api.put).mock.calls[0][1] as any;
 expect(payload.expected_versions).toEqual({1:1});expect(payload.items[0].id).toBe(1);expect(payload.items[0].created_by).toBeUndefined();
 expect(result.current.items[0].created_by?.full_name).toBe('Nguyễn An');expect(result.current.items[0].updated_by?.full_name).toBe('Trần Bình');expect(result.current.dirty).toBe(false);
});
it('keeps drafts on conflict and restores author metadata when reloaded',async()=>{
 vi.mocked(api.put).mockRejectedValue({response:{status:409}});
 const {result,rerender}=renderHook(({data})=>useAnnotations(2,data),{initialProps:{data:initial}});
 act(()=>result.current.update(1,{width:25}));await act(async()=>{await expect(result.current.save()).rejects.toBeTruthy()});
 expect(result.current.dirty).toBe(true);expect(result.current.saving).toBe(false);
 expect(result.current.canUndo).toBe(true);
 rerender({data:[{...initial[0],version:2}]});await waitFor(()=>expect(result.current.dirty).toBe(false));expect(result.current.items[0].created_by?.id).toBe('a');
});

it('undoes create, gesture edit, reclass and delete in order while retaining identity and metadata',()=>{
 const {result}=renderHook(()=>useAnnotations(2,initial));
 act(()=>result.current.add({class_id:3,class_name:'Car',annotation_type:'bbox',x:5,y:5,width:10,height:10}));
 const id=result.current.items[1].id;
 act(()=>{result.current.beginChange();for(let x=6;x<=15;x++)result.current.update(id,{x});result.current.commitChange();});
 expect(result.current.historyLength).toBe(2);
 act(()=>result.current.update(id,{class_id:4,class_name:'Bus'}));
 act(()=>result.current.remove(id));expect(result.current.items).toHaveLength(1);
 act(()=>result.current.undo());expect(result.current.items[1]).toMatchObject({id,class_id:4,x:15});
 act(()=>result.current.undo());expect(result.current.items[1].class_id).toBe(3);
 act(()=>result.current.undo());expect(result.current.items[1].x).toBe(5);
 act(()=>result.current.undo());expect(result.current.items).toEqual(initial);expect(result.current.dirty).toBe(false);
 expect(result.current.canUndo).toBe(false);expect(api.put).not.toHaveBeenCalled();
 act(()=>result.current.remove(1));act(()=>result.current.undo());expect(result.current.items[0]).toEqual(initial[0]);
});

it('ignores no-ops, cancelled and round-trip gestures, and clones polygon points and attribution',()=>{
 const polygon:Annotation[]=[{...initial[0],annotation_type:'polygon',points:[[1,1],[20,1],[20,20]]}];
 const {result}=renderHook(()=>useAnnotations(2,polygon));
 act(()=>{result.current.beginChange();result.current.update(1,{x:4});result.current.update(1,{x:1});result.current.commitChange();});
 expect(result.current.canUndo).toBe(false);
 act(()=>{result.current.beginChange();result.current.update(1,{x:4});result.current.cancelChange();});
 expect(result.current.items[0].x).toBe(1);expect(result.current.canUndo).toBe(false);
 const points:[number,number][]=[[2,2],[20,1],[20,20]];
 act(()=>result.current.update(1,{points,created_by:{id:'spoof',full_name:'Wrong author'},id:300}));
 points[0][0]=999;
 expect(result.current.items[0].points![0][0]).toBe(2);expect(result.current.items[0].created_by).toEqual(initial[0].created_by);
 act(()=>result.current.undo());expect(result.current.items).toEqual(polygon);
 act(()=>result.current.update(1,{x:1}));expect(result.current.canUndo).toBe(false);
});

it('undoes Delete All in one step and saves deletions through the versioned batch',async()=>{
 const {result}=renderHook(()=>useAnnotations(2,initial));
 act(()=>result.current.clear());expect(result.current.historyLength).toBe(1);expect(api.put).not.toHaveBeenCalled();
 act(()=>result.current.undo());expect(result.current.items).toEqual(initial);expect(result.current.dirty).toBe(false);
 act(()=>result.current.clear());vi.mocked(api.put).mockResolvedValue({data:[]});
 await act(async()=>{await result.current.save(4);});
 expect(api.put).toHaveBeenLastCalledWith('/images/2/annotations',{expected_versions:{1:1},expected_revision:4,items:[]});
 expect(result.current.canUndo).toBe(false);
});

const predictions:Prediction[]=[10,11].map(id=>({id,image_id:2,model_class_id:0,model_class_name:'car',mapped_class_id:3,mapped_class_name:'Car',prediction_type:'bbox',x:2,y:2,width:10,height:10,confidence:.9,status:'PENDING',draft_token:`token-${id}`}));
it('applies an AI batch as one undo step, deduplicates it, and persists provenance only on Save',async()=>{
 const {result}=renderHook(()=>useAnnotations(2,initial));
 act(()=>result.current.applyPredictions(predictions));expect(result.current.items).toHaveLength(3);expect(result.current.historyLength).toBe(1);
 act(()=>result.current.applyPredictions(predictions));expect(result.current.historyLength).toBe(1);
 act(()=>result.current.undo());expect(result.current.items).toEqual(initial);expect(api.post).not.toHaveBeenCalled();
 act(()=>result.current.applyPredictions(predictions));vi.mocked(api.put).mockResolvedValue({data:initial});
 await act(async()=>{await result.current.save();});
 expect(vi.mocked(api.put).mock.calls[0][1]).toMatchObject({items:[{id:1},{prediction_id:10,prediction_token:'token-10'},{prediction_id:11,prediction_token:'token-11'}]});
 expect(result.current.canUndo).toBe(false);
});

it('caps history at 50, keeps it after failed Save and resets it on successful Save or image change',async()=>{
 const {result,rerender}=renderHook(({image,data})=>useAnnotations(image,data),{initialProps:{image:2,data:initial}});
 act(()=>{for(let x=2;x<=61;x++)result.current.update(1,{x});});expect(result.current.historyLength).toBe(50);
 vi.mocked(api.put).mockRejectedValueOnce(new Error('Conflict'));
 await act(async()=>{await expect(result.current.save()).rejects.toThrow('Conflict');});expect(result.current.historyLength).toBe(50);
 act(()=>{for(let n=0;n<50;n++)result.current.undo();});expect(result.current.items[0].x).toBe(11);
 vi.mocked(api.put).mockResolvedValue({data:[{...initial[0],x:11,version:2}]});
 await act(async()=>{await result.current.save();});expect(result.current.canUndo).toBe(false);expect(result.current.dirty).toBe(false);
 act(()=>result.current.update(1,{x:12}));rerender({image:3,data:initial});
 await waitFor(()=>expect(result.current.canUndo).toBe(false));expect(result.current.items).toEqual(initial);
});

it('denies locked objects, protects metadata and prevents undo after permission loss',()=>{
 const locked=[{...initial[0],can_edit:false,can_delete:false}];
 const {result,rerender}=renderHook(({editable})=>useAnnotations(2,locked,{editable}),{initialProps:{editable:true}});
 act(()=>{result.current.update(1,{x:8});result.current.remove(1);result.current.clear();});expect(result.current.items).toEqual(locked);expect(result.current.canUndo).toBe(false);
 act(()=>result.current.add({class_id:3,class_name:'Car',annotation_type:'bbox',x:2,y:2,width:5,height:5}));
 rerender({editable:false});expect(result.current.canUndo).toBe(false);act(()=>result.current.undo());expect(result.current.items).toHaveLength(2);
});
