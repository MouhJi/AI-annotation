// @vitest-environment jsdom
import {renderHook,act,waitFor,cleanup} from '@testing-library/react';
import {it,expect,vi,afterEach} from 'vitest';
import {useAnnotations} from './useAnnotations';
import {api} from '../services/api';
import type {Annotation} from '../types';
vi.mock('../services/api',()=>({api:{put:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks()});
const initial:Annotation[]=[{id:1,image_id:2,class_id:3,class_name:'Car',annotation_type:'bbox',x:1,y:1,width:20,height:20,version:1,created_by:{id:'a',full_name:'Nguyễn An'}}];
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
 rerender({data:[{...initial[0],version:2}]});await waitFor(()=>expect(result.current.dirty).toBe(false));expect(result.current.items[0].created_by?.id).toBe('a');
});
