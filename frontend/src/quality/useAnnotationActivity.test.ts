// @vitest-environment jsdom
import {act,cleanup,renderHook} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {api} from '../services/api';
import {useAnnotationActivity} from './useAnnotationActivity';
vi.mock('../services/api',()=>({api:{post:vi.fn()}}));
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.clearAllMocks();});
it('stops heartbeats when hidden or idle and clears its timer on leaving',async()=>{
  vi.useFakeTimers();vi.mocked(api.post).mockResolvedValue({data:{credited_seconds:0}});
  const visibility=vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');
  const hook=renderHook(()=>useAnnotationActivity(8,true,15));await act(async()=>{});
  expect(api.post).toHaveBeenCalledTimes(1);await act(async()=>vi.advanceTimersByTime(10000));expect(api.post).toHaveBeenCalledTimes(2);
  await act(async()=>vi.advanceTimersByTime(10000));expect(api.post).toHaveBeenCalledTimes(2);
  window.dispatchEvent(new Event('pointermove'));visibility.mockReturnValue('hidden');await act(async()=>vi.advanceTimersByTime(10000));expect(api.post).toHaveBeenCalledTimes(2);
  visibility.mockReturnValue('visible');document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('keydown'));
  await act(async()=>vi.advanceTimersByTime(10000));expect(api.post).toHaveBeenCalledTimes(3);
  const body=vi.mocked(api.post).mock.calls[2][1] as any;expect(body.elapsed_seconds).toBeLessThanOrEqual(15);expect(body.sequence).toBe(3);
  hook.unmount();expect(vi.getTimerCount()).toBe(0);
});
