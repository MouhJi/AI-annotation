import {useState} from 'react';
import {api} from '../services/api';
import {Modal} from '../components/Modal';
import type {ReviewDetail} from '../types';
import {ReviewBadge,errorLabels,errorMessage} from './shared';

type Props={imageId:number;review:ReviewDetail;permissions:string[];busy:boolean;dirty:boolean;empty:boolean;onSubmit:(negative:boolean)=>Promise<void>;onChanged:(review:ReviewDetail)=>Promise<void>;onBusy:(busy:boolean)=>void};
export default function ReviewPanel({imageId,review,permissions,busy,dirty,empty,onSubmit,onChanged,onBusy}:Props){
  const [negative,setNegative]=useState(false),[reject,setReject]=useState(false),[reason,setReason]=useState(''),[category,setCategory]=useState('inaccurate_bbox');
  const [error,setError]=useState(''),[snapshot,setSnapshot]=useState<any>(),[snapshotBusy,setSnapshotBusy]=useState(false);
  const can=(permission:string)=>permissions.includes(permission);
  const editable=!['pending_review','approved'].includes(review.state);
  const act=async(action:string)=>{
    if(busy)return;onBusy(true);setError('');
    try{const result=(await api.post(`/images/${imageId}/review/${action}`,{expected_revision:review.revision,expected_review_version:review.review_version,...(action==='reject'?{reason,error_category:category}:{})})).data;
      setReject(false);setReason('');await onChanged(result);
    }catch(e){setError(errorMessage(e,'Review action failed. Reload the image and try again.'));}finally{onBusy(false);}
  };
  const readSnapshot=async(revision:number)=>{setSnapshotBusy(true);setError('');try{setSnapshot((await api.get(`/images/${imageId}/revisions/${revision}`)).data);}catch(e){setError(errorMessage(e,'Unable to load this snapshot.'));}finally{setSnapshotBusy(false);}};
  return <section className="quality-panel" aria-label="Image review"><h3>Image review</h3><ReviewBadge state={review.state}/><p>Revision {review.revision} · {review.open_threads} open discussion{review.open_threads===1?'':'s'}</p>
    {review.negative_confirmed&&!dirty&&empty&&<p>This saved revision is a confirmed negative image with no objects.</p>}
    {review.state==='changes_requested'&&<div className="quality-return" role="status"><b>Changes requested</b><p>{review.history.find(event=>event.action==='changes_requested')?.reason}</p></div>}
    {editable&&can('review.submit')&&<>{empty&&<label className="quality-checkbox"><input type="checkbox" checked={negative} onChange={e=>setNegative(e.target.checked)} disabled={busy}/>This image contains no objects to annotate.</label>}<button disabled={busy||(empty&&!negative)} onClick={()=>void onSubmit(empty&&negative)}>{busy?'Working…':'Submit for review'}</button><p className="muted">Saves the current draft and submits it in one transaction.</p></>}
    {review.state==='pending_review'&&<><p>Annotation editing is locked while this revision is waiting for review.</p>{review.independent_review_required&&can('review.approve')&&<p className="warning">You contributed to this revision. Ask another independent Reviewer, Admin or Owner to approve it. Add a reviewer if nobody else can review.</p>}<div className="quality-actions">{can('review.approve')&&<button disabled={busy||!review.can_approve||dirty} onClick={()=>void act('approve')}>Approve</button>}{can('review.reject')&&<button className="secondary" disabled={busy||dirty} onClick={()=>setReject(true)}>Request changes</button>}{review.can_withdraw&&<button className="secondary" disabled={busy||dirty} onClick={()=>void act('withdraw')}>Withdraw submission</button>}</div></>}
    {review.state==='approved'&&<><p>This revision is approved. Reopen it before making changes; export eligibility will be removed.</p>{can('review.reopen')&&<button className="secondary" disabled={busy||dirty} onClick={()=>void act('reopen')}>Reopen for editing</button>}</>}
    <details><summary>Contributors ({review.contributors.length})</summary>{review.contributors.length?<ul>{review.contributors.map(person=><li key={person.id}>{person.full_name}</li>)}</ul>:<p>Historical contributors are unknown.</p>}</details>
    <details className="quality-history"><summary>Review history</summary>{!review.history.length?<p>No recorded review events yet.</p>:review.history.map(event=><article key={event.id}><b>{event.action.split('_').join(' ')}</b><small>{event.actor?.full_name??'Unknown user'} · {new Date(event.created_at).toLocaleString()}</small><p>{event.reason}{event.error_category&&' · '+errorLabels[event.error_category]}</p><button className="link-button" disabled={snapshotBusy} onClick={()=>void readSnapshot(event.revision)}>View revision {event.revision}</button></article>)}</details>
    {error&&<p className="error" role="alert">{error}</p>}
    {reject&&<Modal title="Request changes" onClose={()=>!busy&&setReject(false)}><form className="form-stack" onSubmit={event=>{event.preventDefault();void act('reject');}}><label>Error category<select value={category} onChange={event=>setCategory(event.target.value)}>{Object.entries(errorLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label>Reason (required)<textarea required maxLength={4000} value={reason} onChange={event=>setReason(event.target.value)}/></label><div className="modal-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>setReject(false)}>Cancel</button><button disabled={busy||!reason.trim()}>Request changes</button></div></form></Modal>}
    {snapshot&&<Modal title={'Revision '+snapshot.revision+' snapshot'} onClose={()=>setSnapshot(undefined)}><p>Immutable snapshot #{snapshot.id} · {snapshot.objects.length} objects{snapshot.negative_confirmed?' · Confirmed negative image':''}</p><div className="quality-snapshot">{snapshot.objects.map((object:any)=><article key={object.id}><b>#{object.id} · {object.class_name}</b><p>{object.annotation_type==='polygon'?object.points_json:`x ${object.x}, y ${object.y}, width ${object.width}, height ${object.height}`}</p></article>)}</div></Modal>}
  </section>;
}
