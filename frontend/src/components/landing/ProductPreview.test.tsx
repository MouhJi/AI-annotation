// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import ProductPreview from './ProductPreview';

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();});
const objectList=()=>within(screen.getByRole('complementary',{name:'Sample objects'}));
const selected=(name:string)=>objectList().getByRole('button',{name:new RegExp(name)}).getAttribute('aria-pressed');

it('changes geometry and selects objects with keyboard while keeping the demo explicitly local',()=>{
  const {container}=render(<ProductPreview/>);
  expect(selected('Car')).toBe('true');
  fireEvent.click(screen.getByRole('button',{name:'Polygon'}));
  expect(container.querySelectorAll('.lp-demo-geometry polygon')).toHaveLength(3);
  fireEvent.keyDown(screen.getByRole('button',{name:'Select sample Person'}),{key:'Enter'});
  expect(selected('Person')).toBe('true');expect(screen.getByRole('button',{name:'Play preview'})).toBeTruthy();
  fireEvent.keyDown(screen.getByRole('button',{name:'Select sample Tree'}),{key:' '});
  expect(selected('Tree')).toBe('true');
  fireEvent.click(screen.getByRole('button',{name:'Bounding box'}));
  expect(container.querySelectorAll('.lp-demo-geometry polygon')).toHaveLength(0);
  expect(screen.getByText('Local preview. No AI inference runs here.')).toBeTruthy();
});
it('pauses autoplay on interaction, offscreen and hidden tabs, and removes its timer on unmount',()=>{
  vi.useFakeTimers();let observer!:(entries:{isIntersecting:boolean}[])=>void;
  vi.stubGlobal('IntersectionObserver',class {observe=vi.fn();disconnect=vi.fn();constructor(callback:typeof observer){observer=callback;}});
  const visibility=vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');
  const result=render(<ProductPreview/>);
  act(()=>vi.advanceTimersByTime(6400));expect(selected('Car')).toBe('true');
  act(()=>observer([{isIntersecting:true}]));act(()=>vi.advanceTimersByTime(3200));expect(selected('Person')).toBe('true');
  fireEvent.click(objectList().getByRole('button',{name:/Tree/}));act(()=>vi.advanceTimersByTime(9600));expect(selected('Tree')).toBe('true');
  fireEvent.click(screen.getByRole('button',{name:'Play preview'}));act(()=>vi.advanceTimersByTime(3200));expect(selected('Car')).toBe('true');
  act(()=>observer([{isIntersecting:false}]));act(()=>vi.advanceTimersByTime(6400));expect(selected('Car')).toBe('true');
  act(()=>observer([{isIntersecting:true}]));visibility.mockReturnValue('hidden');fireEvent(document,new Event('visibilitychange'));
  act(()=>vi.advanceTimersByTime(6400));expect(selected('Car')).toBe('true');
  visibility.mockReturnValue('visible');fireEvent(document,new Event('visibilitychange'));act(()=>vi.advanceTimersByTime(3200));expect(selected('Person')).toBe('true');
  result.unmount();expect(vi.getTimerCount()).toBe(0);
});
it('honors reduced motion and stops a running tour when the preference changes',()=>{
  vi.useFakeTimers();let preference!:()=>void;
  const media={matches:true,addEventListener:vi.fn((_:string,callback:()=>void)=>{preference=callback;}),removeEventListener:vi.fn()};
  vi.stubGlobal('matchMedia',()=>media);
  render(<ProductPreview/>);
  expect((screen.getByRole('button',{name:'Preview uses reduced motion'}) as HTMLButtonElement).disabled).toBe(true);
  act(()=>vi.advanceTimersByTime(9600));expect(selected('Car')).toBe('true');
  act(()=>{media.matches=false;preference();});fireEvent.click(screen.getByRole('button',{name:'Play preview'}));
  expect(screen.getByRole('button',{name:'Pause preview'})).toBeTruthy();
  act(()=>{media.matches=true;preference();});expect(vi.getTimerCount()).toBe(0);
  expect((screen.getByRole('button',{name:'Preview uses reduced motion'}) as HTMLButtonElement).disabled).toBe(true);
});
