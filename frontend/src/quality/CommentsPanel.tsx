import {useEffect,useRef,useState} from 'react';
import {api} from '../services/api';
import type {DiscussionThread} from '../types';
import {errorMessage} from './shared';

type Props={imageId:number;selected?:number;canComment:boolean;onSelectObject:(id:number)=>void;onChanged:()=>void};
export default function CommentsPanel({imageId,selected,canComment,onSelectObject,onChanged}:Props){
  const [threads,setThreads]=useState<DiscussionThread[]>([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [body,setBody]=useState(''),[scope,setScope]=useState('image'),[replies,setReplies]=useState<Record<number,string>>({}),[filter,setFilter]=useState('all');
  const generation=useRef(0),pending=useRef(false);
  const load=async()=>{const token=++generation.current;try{const result=(await api.get(`/images/${imageId}/threads`)).data;if(token===generation.current)setThreads(result);}catch(e){if(token===generation.current)setError(errorMessage(e,'Unable to load discussions.'));}finally{if(token===generation.current)setLoading(false);}};
  useEffect(()=>{void load();return()=>{generation.current++;};},[imageId]);
  const mutate=async(action:()=>Promise<unknown>,success:()=>void)=>{
    if(pending.current)return;pending.current=true;setBusy(true);setError('');
    try{await action();success();await load();onChanged();}catch(e){setError(errorMessage(e,'Unable to update the discussion. Reload and try again.'));}finally{pending.current=false;setBusy(false);}
  };
  const hasSavedObject=selected!==undefined&&selected>0;
  return <section className="quality-panel" aria-label="Image and object discussions"><h3>Discussions</h3><p>Open threads help reviewers check issues. They do not block approval or change annotation revisions.</p>
    {canComment&&<form className="form-stack" onSubmit={event=>{event.preventDefault();void mutate(()=>api.post(`/images/${imageId}/threads`,{body,object_id:scope==='object'?selected:null}),()=>setBody(''));}}><label>Discussion scope<select disabled={busy} value={scope} onChange={event=>setScope(event.target.value)}><option value="image">Whole image</option><option value="object" disabled={!hasSavedObject}>Selected object{hasSavedObject?' #'+selected:''}</option></select></label>{!hasSavedObject&&<small>Select a saved object to attach a discussion. Save new objects first.</small>}<label>Comment<textarea required maxLength={4000} value={body} onChange={event=>setBody(event.target.value)} disabled={busy}/></label><button disabled={busy||!body.trim()||(scope==='object'&&!hasSavedObject)}>Start discussion</button></form>}
    <label>Show discussions<select value={filter} onChange={event=>setFilter(event.target.value)}><option value="all">All threads</option><option value="open">Open</option><option value="resolved">Resolved</option></select></label>
    {loading?<p role="status">Loading discussions…</p>:!threads.length?<p>No discussions yet. Add an image or object comment to start a review conversation.</p>:<div className="quality-threads">{threads.filter(thread=>filter==='all'||thread.resolved===(filter==='resolved')).map(thread=><article key={thread.id} className={thread.resolved?'is-resolved':''}>
      <div className="quality-thread-heading">{thread.object_id===null?<b>Image discussion</b>:thread.object_deleted?<b>Object deleted · #{thread.object_id}</b>:<button className="link-button" onClick={()=>onSelectObject(thread.object_id!)}>Select object #{thread.object_id}</button>}<span className="badge">{thread.resolved?'Resolved':'Open'}</span></div>
      {thread.comments.map(comment=><div className="quality-comment" key={comment.id}><b>{comment.author?.full_name??'Deleted user'}</b><small>{new Date(comment.created_at).toLocaleString()}</small><p>{comment.body}</p></div>)}
      {thread.resolved_at&&<small>{thread.resolved?'Resolved by':'Last resolved by'} {thread.resolved_by?.full_name??'Deleted user'} · {new Date(thread.resolved_at).toLocaleString()}</small>}
      {canComment&&<form onSubmit={event=>{event.preventDefault();void mutate(()=>api.post(`/threads/${thread.id}/comments`,{body:replies[thread.id]}),()=>setReplies(values=>({...values,[thread.id]:''})));}}><label>Reply to thread #{thread.id}<textarea required maxLength={4000} disabled={busy} value={replies[thread.id]??''} onChange={event=>setReplies(values=>({...values,[thread.id]:event.target.value}))}/></label><button className="secondary" disabled={busy||!replies[thread.id]?.trim()}>Reply</button></form>}
      {thread.can_resolve&&<button className="secondary" disabled={busy} onClick={()=>void mutate(()=>api.patch(`/threads/${thread.id}`,{resolved:!thread.resolved,expected_version:thread.version}),()=>{})}>{thread.resolved?'Reopen thread':'Resolve thread'}</button>}
    </article>)}</div>}
    {error&&<div role="alert"><p className="error">{error}</p><button className="secondary" disabled={busy} onClick={()=>void load()}>Reload discussions</button></div>}
  </section>;
}
