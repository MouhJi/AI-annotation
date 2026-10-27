// @vitest-environment jsdom
import {act,cleanup,render,screen} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import ProtectedImage from './ProtectedImage';
import AnnotationCanvas from './AnnotationCanvas';
import {api} from '../services/api';

vi.mock('../services/api',()=>({api:{get:vi.fn()}}));
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.clearAllMocks();});
it('reports request failure in the editor and disables drawing until an image is loaded',async()=>{
  vi.mocked(api.get).mockRejectedValueOnce(new Error('unavailable'));
  const {container}=render(<AnnotationCanvas src='/failed.png' imageWidth={1000} imageHeight={800} annotations={[]} classes={[]} mode='draw' onSelect={vi.fn()} onAdd={vi.fn()} onChange={vi.fn()}/>);
  await screen.findByText('Unable to load this image file.');
  expect(container.querySelector('svg')).toBeNull();expect((screen.getByRole('button',{name:'Zoom in'}) as HTMLButtonElement).disabled).toBe(true);
});
it('does not refetch on callback changes, ignores stale image errors and revokes object URLs',async()=>{
  const create=vi.fn(()=> 'blob:new-image'),revoke=vi.fn();
  const createDescriptor=Object.getOwnPropertyDescriptor(URL,'createObjectURL'),revokeDescriptor=Object.getOwnPropertyDescriptor(URL,'revokeObjectURL');
  Object.defineProperty(URL,'createObjectURL',{value:create,configurable:true});Object.defineProperty(URL,'revokeObjectURL',{value:revoke,configurable:true});
  try{
    let rejectOld!:(error:Error)=>void;
    vi.mocked(api.get).mockImplementationOnce(()=>new Promise((_,reject)=>{rejectOld=reject;})).mockResolvedValueOnce({data:new Blob(['image'])});
    const failure=vi.fn(),result=render(<ProtectedImage src='/old.png' alt='target' onLoadFailure={failure}/>);
    result.rerender(<ProtectedImage src='/new.png' alt='target' onLoadFailure={failure}/>);
    await screen.findByAltText('target');
    result.rerender(<ProtectedImage src='/new.png' alt='target' onLoadFailure={()=>failure()}/>);
    await act(async()=>{rejectOld(new Error('old request failed'));});
    expect(api.get).toHaveBeenCalledTimes(2);expect(failure).not.toHaveBeenCalled();expect(screen.queryByLabelText('Unable to load image')).toBeNull();
    result.unmount();expect(revoke).toHaveBeenCalledWith('blob:new-image');
  }finally{
    if(createDescriptor)Object.defineProperty(URL,'createObjectURL',createDescriptor);else Reflect.deleteProperty(URL,'createObjectURL');
    if(revokeDescriptor)Object.defineProperty(URL,'revokeObjectURL',revokeDescriptor);else Reflect.deleteProperty(URL,'revokeObjectURL');
  }
});
