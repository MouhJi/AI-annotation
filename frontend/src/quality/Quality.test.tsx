// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {MemoryRouter} from 'react-router-dom';
import {api} from '../services/api';
import type {ReviewDetail,DiscussionThread} from '../types';
import ReviewPanel from './ReviewPanel';
import CommentsPanel from './CommentsPanel';
import QualityDashboard from './QualityDashboard';
import ReviewQueue from './ReviewQueue';
vi.mock('../services/api',()=>({api:{get:vi.fn(),post:vi.fn(),patch:vi.fn()}}));
const review:ReviewDetail={state:'in_progress',revision:7,review_version:9,approved_revision:null,negative_confirmed:false,snapshot_id:10,contributors:[{id:'a',full_name:'Original creator'}],can_approve:false,can_withdraw:false,independent_review_required:true,open_threads:1,idle_seconds:60,history:[]};
beforeEach(()=>vi.clearAllMocks());afterEach(cleanup);
function panel(overrides:Partial<Parameters<typeof ReviewPanel>[0]>={}){const onSubmit=vi.fn().mockResolvedValue(undefined),onChanged=vi.fn().mockResolvedValue(undefined);render(<ReviewPanel imageId={2} review={review} permissions={['review.submit','review.approve','review.reject','review.reopen']} busy={false} dirty={false} empty={true} onSubmit={onSubmit} onChanged={onChanged} onBusy={vi.fn()} {...overrides}/>);return {onSubmit,onChanged};}
it('requires explicit negative confirmation and does not treat draft saving as submission',()=>{
  const {onSubmit}=panel();const button=screen.getByRole('button',{name:'Submit for review'});
  expect((button as HTMLButtonElement).disabled).toBe(true);fireEvent.click(button);expect(onSubmit).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('checkbox',{name:'This image contains no objects to annotate.'}));fireEvent.click(button);
  expect(onSubmit).toHaveBeenCalledWith(true);expect(api.post).not.toHaveBeenCalled();
});
it('blocks a contributor approval in the UI and sends a versioned return with a required reason',async()=>{
  const changed={...review,state:'changes_requested'};vi.mocked(api.post).mockResolvedValue({data:changed});
  const {onChanged}=panel({review:{...review,state:'pending_review',can_withdraw:true},empty:false});
  expect((screen.getByRole('button',{name:'Approve'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/another independent Reviewer/)).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Request changes'}));
  const modal=screen.getByRole('dialog');expect((within(modal).getByRole('button',{name:'Request changes'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(within(modal).getByLabelText('Reason (required)'),{target:{value:'Adjust the outline.'}});
  fireEvent.change(within(modal).getByLabelText('Error category'),{target:{value:'inaccurate_polygon'}});
  fireEvent.click(within(modal).getByRole('button',{name:'Request changes'}));
  await waitFor(()=>expect(onChanged).toHaveBeenCalledWith(changed));
  expect(api.post).toHaveBeenCalledWith('/images/2/review/reject',{expected_revision:7,expected_review_version:9,reason:'Adjust the outline.',error_category:'inaccurate_polygon'});
});
it('retains the review on conflict and offers a concrete reload error',async()=>{
  vi.mocked(api.post).mockRejectedValue({response:{data:{detail:'Revision changed. Reload the image.'}}});
  const {onChanged}=panel({review:{...review,state:'approved'},empty:false});fireEvent.click(screen.getByRole('button',{name:'Reopen for editing'}));
  await screen.findByText('Revision changed. Reload the image.');expect(onChanged).not.toHaveBeenCalled();
});
const thread:DiscussionThread={id:51,object_id:99,object_deleted:false,resolved:false,version:3,resolved_by:null,resolved_at:null,can_resolve:true,comments:[{id:1,author:{id:'a',full_name:'Reviewer one'},body:'Check the left edge.',created_at:'2026-10-01T01:00:00Z'}]};
it('selects a stable object ID, retains deleted object discussions and version checks resolution',async()=>{
  vi.mocked(api.get).mockResolvedValue({data:[thread,{...thread,id:52,object_id:44,object_deleted:true}]});
  vi.mocked(api.patch).mockResolvedValue({data:{id:51}});const onSelect=vi.fn();
  render(<CommentsPanel imageId={2} canComment={true} selected={99} onSelectObject={onSelect} onChanged={vi.fn()}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Select object #99'}));expect(onSelect).toHaveBeenCalledWith(99);
  expect(screen.getByText('Object deleted · #44')).toBeTruthy();expect(screen.queryByRole('button',{name:'Select object #44'})).toBeNull();
  fireEvent.click(screen.getAllByRole('button',{name:'Resolve thread'})[0]);
  await waitFor(()=>expect(api.patch).toHaveBeenCalledWith('/threads/51',{resolved:true,expected_version:3}));
  expect(api.post).not.toHaveBeenCalled();
});
it('does not allow attaching a discussion to an unsaved draft object',async()=>{
  vi.mocked(api.get).mockResolvedValue({data:[]});render(<CommentsPanel imageId={2} selected={-1} canComment={true} onSelectObject={vi.fn()} onChanged={vi.fn()}/>);
  await screen.findByText(/No discussions yet/);expect((screen.getByRole('option',{name:'Selected object'}) as HTMLOptionElement).disabled).toBe(true);
  expect(screen.getByText(/Save new objects first/)).toBeTruthy();
});
it('shows no-data quality rates and actual separate counters without a ranking',async()=>{
  vi.mocked(api.get).mockResolvedValue({data:{unique_submitted_images:0,submissions:0,approved_images:0,returns:0,first_pass_rate:null,first_pass_approved:0,first_pass_decided:0,average_rework_rounds:null,active_seconds:0,can_view_project:false,people:[],errors:[],contributors:[],object_sources:{unknown:0},history_note:'Older work is not estimated.',time_note:'Estimated active time only.',start:'2026-10-01',end:'2026-11-01'}});
  render(<QualityDashboard projectId="3"/>);expect(await screen.findAllByText('No data yet')).toHaveLength(2);expect(screen.queryByLabelText('User')).toBeNull();
  fireEvent.change(screen.getByLabelText('From (UTC)'),{target:{value:'2026-10-01'}});fireEvent.change(screen.getByLabelText('Through (UTC)'),{target:{value:'2026-10-02'}});fireEvent.click(screen.getByRole('button',{name:'Apply filters'}));
  await waitFor(()=>expect(api.get).toHaveBeenLastCalledWith('/projects/3/quality',{params:expect.objectContaining({start:'2026-10-01T00:00:00Z',end:'2026-10-03T00:00:00.000Z'})}));
});
it('loads a scoped queue and opens the existing image route',async()=>{
  vi.mocked(api.get).mockResolvedValue({data:{total:1,items:[{id:5,filename:'review.png',annotation_count:1,revision:2,review_state:'pending_review',split:'val'}]}});
  render(<MemoryRouter><ReviewQueue projectId="3"/></MemoryRouter>);expect((await screen.findByRole('link',{name:'review.png'})).getAttribute('href')).toBe('/projects/3/images/5');
  fireEvent.change(screen.getByLabelText('Review status'),{target:{value:'changes_requested'}});fireEvent.change(screen.getByLabelText('Dataset split'),{target:{value:'val'}});
  await waitFor(()=>expect(api.get).toHaveBeenLastCalledWith('/projects/3/review-queue',{params:{state:'changes_requested',split:'val',offset:0,limit:50}}));
});
