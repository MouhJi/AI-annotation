import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {useWorkspace} from "../workspaces/WorkspaceProvider";
import AnnotationCanvas from "../components/AnnotationCanvas";
import AnnotationAttribution, {annotationLabel} from "../components/AnnotationAttribution";
import AutoLabelPanel from "../components/AutoLabelPanel";
import { useAnnotations } from "../hooks/useAnnotations";
import { api, imageUrl } from "../services/api";
import type { Annotation, ImageDetail, ImageItem, LabelClass, Prediction, Project, ReviewDetail } from "../types";
import ReviewPanel from '../quality/ReviewPanel';
import CommentsPanel from '../quality/CommentsPanel';
import {ReviewBadge,errorMessage} from '../quality/shared';
import {useAnnotationActivity} from '../quality/useAnnotationActivity';

export default function EditorPage() {
  const {current}=useWorkspace();
  const { projectId, imageId } = useParams(); const navigate = useNavigate();
  const [project, setProject] = useState<Project>(); const [image, setImage] = useState<ImageDetail>(); const [classes, setClasses] = useState<LabelClass[]>([]); const [allImages, setAllImages] = useState<ImageItem[]>([]); const [initial, setInitial] = useState<Annotation[]>([]); const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [classId, setClassId] = useState<number>(); const [selected, setSelected] = useState<number>(); const [selectedPrediction, setSelectedPrediction] = useState<number>(); const [mode, setMode] = useState<"select" | "draw" | "polygon">("select");
  const [loadError, setLoadError] = useState(""); const [actionError, setActionError] = useState("");
  const [resetViewportKey, setResetViewportKey] = useState(0);
  const [review,setReview]=useState<ReviewDetail>(),[reviewBusy,setReviewBusy]=useState(false),[panel,setPanel]=useState<'objects'|'review'|'comments'>('objects'),[message,setMessage]=useState('');
  const loadGeneration = useRef(0);
  const annotations = useAnnotations(Number(imageId), initial);
  const busy=annotations.saving||reviewBusy;
  const workflowLocked=review?.state==='pending_review'||review?.state==='approved';
  useAnnotationActivity(Number(imageId),!!project?.permissions.includes('activity.record'),review?.idle_seconds);
  useEffect(()=>{window.dispatchEvent(new CustomEvent('annotation-dirty',{detail:annotations.dirty}));return()=>{window.dispatchEvent(new CustomEvent('annotation-dirty',{detail:false}))}},[annotations.dirty]);
  const load = () => {const generation=++loadGeneration.current; return Promise.all([api.get(`/projects/${projectId}`), api.get(`/images/${imageId}`), api.get(`/images/${imageId}/annotations`), api.get(`/projects/${projectId}/classes`), api.get(`/projects/${projectId}/images`),api.get(`/images/${imageId}/review`)]).then(([projectResponse, imageResponse, annotationsResponse, classesResponse, imagesResponse,reviewResponse]) => {
    if(generation!==loadGeneration.current)return;
    if(projectResponse.data.workspace_id!==current?.id||imageResponse.data.project_id!==Number(projectId)){setProject(undefined);setImage(undefined);setLoadError("Access denied: image does not belong to the current workspace/project.");return;}
    setProject(projectResponse.data); setImage(imageResponse.data); setInitial(Array.isArray(annotationsResponse.data) ? annotationsResponse.data : []); setClasses(Array.isArray(classesResponse.data) ? classesResponse.data : []); setAllImages(Array.isArray(imagesResponse.data) ? imagesResponse.data : []); setLoadError("");
    setReview(typeof reviewResponse.data?.revision==='number'?reviewResponse.data:undefined);
  }).catch((error) => { if(generation!==loadGeneration.current)return;setProject(undefined);setImage(undefined);const detail = error.response?.data?.detail; setLoadError(typeof detail === "string" ? detail : "Unable to load the image editor. Check that the API is running, then retry."); });};
  useEffect(() => { setImage(undefined);setProject(undefined);setReview(undefined);setPredictions([]);setLoadError("");void load();return()=>{loadGeneration.current++;}; }, [imageId, projectId, current?.id]);
  useEffect(() => { setSelected(undefined); setSelectedPrediction(undefined); setMode("select"); setActionError("");setMessage('');setPanel('objects'); }, [imageId]);
  useEffect(() => { const onKeyDown = (event: KeyboardEvent) => { if (!event.defaultPrevented && !busy && !workflowLocked && project?.permissions.includes("annotation.delete") && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) && (event.key === "Delete" || event.key === "Backspace") && selected && annotations.items.some(a=>a.id===selected&&(a.isNew||a.can_delete)) && mode === "select") { annotations.remove(selected); setSelected(undefined); } }; window.addEventListener("keydown", onKeyDown); return () => window.removeEventListener("keydown", onKeyDown); }, [selected, annotations, mode, project,busy,workflowLocked]);
  if (loadError) return <main className="editor-error"><section><p className="eyebrow">ANNOTATION EDITOR</p><h1>Unable to open this image</h1><p>{loadError}</p><button onClick={() => navigate(`/projects/${projectId}`)}>← Back to project</button></section></main>;
  if (!image || image.id!==Number(imageId) || !project) return <main className="editor-loading">Loading image editor…</main>;
  const can=(permission:string)=>project.permissions.includes(permission); const readOnly=!can("annotation.update")||workflowLocked;
  const segmentation = project.annotation_mode === "instance_segmentation"; const index = allImages.findIndex((item) => item.id === image.id);
  const go = (nextIndex: number) => { if(busy)return; if (annotations.dirty && !window.confirm("You have unsaved changes. Discard changes?")) return; const next = allImages[nextIndex]; if (next) navigate(`/projects/${projectId}/images/${next.id}`); };
  const deleteAll = async () => {
    if(!can("annotation.delete")||readOnly||busy)return;
    if (!window.confirm("Delete all labels?\n\nThis removes labels from the dataset. Deletion history is retained.")) return;
    setReviewBusy(true);
    try { setActionError(""); const result = await api.delete(`/images/${image.id}/annotations`,{data:{expected_versions:Object.fromEntries(initial.map(a=>[a.id,a.version]))}}); annotations.replace([]); setInitial([]); setSelected(undefined); await load(); setMessage(`Deleted ${result.data.deleted_count} saved labels.`); }
    catch (error: any) { setActionError(errorMessage(error,"Unable to delete labels")); }finally{setReviewBusy(false);}
  };
  const refreshReview=async()=>{try{const result=(await api.get(`/images/${image.id}/review`)).data;if(typeof result?.revision==='number')setReview(result);}catch(error){setActionError(errorMessage(error,'Unable to refresh review status. Reload the image.'));}};
  const save = async () => { if(readOnly||busy)return;setReviewBusy(true); try { setActionError(""); const saved=await annotations.save(review?.revision);setInitial(saved);setResetViewportKey(value=>value+1);setMessage("Draft saved. It has not been submitted for review.");await refreshReview(); } catch (error: any) { setActionError(errorMessage(error,"Save failed")); }finally{setReviewBusy(false);} };
  const submit=async(negative:boolean)=>{if(!review||readOnly||busy)return;setActionError('');setMessage('');try{const result=await annotations.submit(review,negative);setInitial(result.annotations);setReview(result.review);setMode('select');setPredictions([]);setResetViewportKey(value=>value+1);setMessage('Revision submitted for review. Editing is locked.');}catch(error){setActionError(errorMessage(error,'Unable to submit. Your draft and viewport have been retained.'));}};
  const selectObject=(id:number)=>{if(!annotations.items.some(item=>item.id===id))return;setSelected(id);setSelectedPrediction(undefined);setMode('select');setPanel('objects');window.requestAnimationFrame(()=>document.getElementById('annotation-object-'+id)?.scrollIntoView?.({block:'nearest'}));};
  const reload=()=>{if(busy)return;if(annotations.dirty&&!window.confirm('Reload this image and discard unsaved changes?'))return;void load();};
  return <main className="editor"><header><button disabled={busy} onClick={() => {if(!annotations.dirty||window.confirm('Discard unsaved changes?'))navigate(`/projects/${projectId}`);}}>← Back</button><h2>{image.filename}</h2><ReviewBadge state={review?.state}/>{review&&<button className="secondary" onClick={()=>setPanel('review')}>Review</button>}{!readOnly?<button disabled={busy} onClick={() => void save()}>{annotations.saving ? "Saving…" : "Save draft"}</button>:<span className="badge">{workflowLocked?'Editing locked':'Read only · Viewer'}</span>}</header>
    {message&&<p className="quality-save-status" role="status">{message}</p>}{actionError&&<div role="alert"><p className="error">{actionError}</p><button className="secondary" disabled={busy} onClick={reload}>Reload image</button></div>}
    <div className="workspace"><aside><h3>Classes</h3>{classes.map(item=><button disabled={busy||readOnly} className={classId===item.id?'active':''} onClick={()=>setClassId(item.id)} key={item.id}>● {item.name}</button>)}
      {can('prediction.run')&&!readOnly&&!busy&&(annotations.dirty?<p className="muted">Save your draft before running or accepting AI suggestions.</p>:<AutoLabelPanel key={image.id} projectId={projectId!} imageId={image.id} classes={classes} annotationMode={project.annotation_mode} selectedId={selectedPrediction} onSelect={id=>{setSelectedPrediction(id);setSelected(undefined);}} onPredictions={setPredictions} onAccepted={()=>void load()}/>)}
    </aside>
    <AnnotationCanvas key={image.id} resetViewportKey={resetViewportKey} readOnly={readOnly||busy} src={imageUrl(image.image_url)} imageWidth={image.width} imageHeight={image.height} annotations={annotations.items} predictions={predictions} classes={classes} selected={selected} selectedPrediction={selectedPrediction} classId={classId} mode={mode} onSelect={id=>{setSelected(id);setSelectedPrediction(undefined);}} onSelectPrediction={id=>{setSelectedPrediction(id);setSelected(undefined);}} onAdd={annotation=>{annotations.add(annotation);setMode('select');}} onChange={annotations.update}/>
    <aside className="quality-sidebar"><div className="quality-sidebar-tabs" aria-label="Annotation details"><button className="secondary" aria-pressed={panel==='objects'} onClick={()=>setPanel('objects')}>Objects</button>{review&&<button className="secondary" aria-pressed={panel==='review'} onClick={()=>setPanel('review')}>Image review</button>}{can('comment.read')&&<button className="secondary" aria-pressed={panel==='comments'} onClick={()=>setPanel('comments')}>Discussions ({review?.open_threads??0})</button>}</div>
      <div hidden={panel!=='objects'} className="quality-object-list"><h3>Objects</h3>{annotations.items.map(annotation=><button id={'annotation-object-'+annotation.id} className={selected===annotation.id?'active':''} onClick={()=>{setSelected(annotation.id);setSelectedPrediction(undefined);}} key={annotation.id}>{annotationLabel(annotation)}</button>)}
        {annotations.items.find(item=>item.id===selected)&&<><label>Object class<select disabled={readOnly||busy||!annotations.items.some(a=>a.id===selected&&(a.isNew||a.can_edit))} value={annotations.items.find(a=>a.id===selected)?.class_id} onChange={event=>{const c=classes.find(c=>c.id===Number(event.target.value));if(c&&selected!==undefined)annotations.update(selected,{class_id:c.id,class_name:c.name});}}>{classes.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><AnnotationAttribution annotation={annotations.items.find(item=>item.id===selected)!}/>{!readOnly&&!annotations.items.some(a=>a.id===selected&&(a.isNew||a.can_edit))&&<p>Read only object: creator role does not permit correction.</p>}</>}
      </div>
      {review&&<div hidden={panel!=='review'}><ReviewPanel key={image.id} imageId={image.id} review={review} permissions={project.permissions} busy={busy} dirty={annotations.dirty} empty={annotations.items.length===0} onSubmit={submit} onBusy={setReviewBusy} onChanged={async next=>{setReview(next);setMode('select');await load();}}/></div>}
      {can('comment.read')&&<div hidden={panel!=='comments'}><CommentsPanel key={image.id} imageId={image.id} selected={selected} canComment={can('comment.create')} onSelectObject={selectObject} onChanged={()=>void refreshReview()}/></div>}
    </aside></div>
    <footer>{!readOnly&&<><button disabled={busy} className={mode==='select'?'active':''} onClick={()=>setMode('select')}>Select</button>{segmentation?<button disabled={busy} className={mode==='polygon'?'active':''} onClick={()=>setMode('polygon')}>Polygon</button>:<button disabled={busy} className={mode==='draw'?'active':''} onClick={()=>setMode('draw')}>Bounding Box</button>}<button disabled={busy||!annotations.items.some(a=>a.id===selected&&(a.isNew||a.can_delete))} onClick={()=>{if(selected){annotations.remove(selected);setSelected(undefined);}}}>Delete</button><button className="danger" disabled={busy||initial.some(a=>!a.can_delete)} onClick={()=>void deleteAll()}>Delete All Labels</button></>}<span/><button disabled={busy||index<=0} onClick={()=>go(index-1)}>‹ Previous</button><button disabled={busy||index===allImages.length-1} onClick={()=>go(index+1)}>Next ›</button></footer>
  </main>;
}
