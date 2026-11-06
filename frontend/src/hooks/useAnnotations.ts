import {useEffect,useMemo,useRef,useState} from 'react';
import type {Annotation,DraftAnnotation,Prediction,ReviewDetail} from '../types';
import {api} from '../services/api';

const same = (a:DraftAnnotation,b:DraftAnnotation) =>
  ['class_id','annotation_type','x','y','width','height','prediction_id','prediction_token'].every(k=>a[k as keyof DraftAnnotation]===b[k as keyof DraftAnnotation])
  && JSON.stringify(a.points??null)===JSON.stringify(b.points??null);
const equal = (a:DraftAnnotation[],b:DraftAnnotation[]) => a.length===b.length && a.every((item,i)=>item.id===b[i].id && same(item,b[i]));
type Permissions = {editable?:boolean;canCreate?:boolean;canUpdate?:boolean;canDelete?:boolean;canReviewPredictions?:boolean};
type DraftState = {items:DraftAnnotation[];original:Annotation[];history:DraftAnnotation[][];transaction:DraftAnnotation[]|null};

export function useAnnotations(imageId:number,initial:Annotation[],permissions:Permissions={}) {
  const savingRef=useRef(false),nextId=useRef(-1),imageRef=useRef(imageId);
  imageRef.current=imageId;
  const [saving,setSaving]=useState(false);
  const [state,setState]=useState<DraftState>(()=>({items:structuredClone(initial),original:structuredClone(initial),history:[],transaction:null}));
  const stateRef=useRef(state);
  const write=(next:DraftState)=>{stateRef.current=next;setState(next);};
  const editable=permissions.editable!==false&&!savingRef.current;
  const canCreate=permissions.canCreate!==false,canUpdate=permissions.canUpdate!==false,canDelete=permissions.canDelete!==false;
  const reset=(next:Annotation[])=>write({items:structuredClone(next),original:structuredClone(next),history:[],transaction:null});
  useEffect(()=>{nextId.current=-1;reset(initial);},[imageId,initial]);
  const change=(transform:(items:DraftAnnotation[])=>DraftAnnotation[])=>{
    if(!editable||savingRef.current)return false;
    const current=stateRef.current,next=transform(current.items);
    if(equal(current.items,next))return false;
    write({...current,items:structuredClone(next),history:current.transaction?current.history:[...current.history,structuredClone(current.items)].slice(-50)});
    return true;
  };
  const update=(id:number,patch:Partial<DraftAnnotation>)=>change(items=>items.map(a=>{
    if(a.id!==id||!canUpdate||(!a.isNew&&!a.can_edit))return a;
    // Geometry/class are editable; identity, attribution and permission flags are not.
    const allowed=Object.fromEntries(Object.entries(patch).filter(([key])=>['class_id','class_name','annotation_type','x','y','width','height','points'].includes(key)));
    return {...a,...structuredClone(allowed)};
  }));
  const add=(box:Omit<DraftAnnotation,'id'|'isNew'>)=>canCreate&&change(items=>[...items,{...structuredClone(box),id:nextId.current--,isNew:true}]);
  const remove=(id:number)=>canDelete&&change(items=>items.filter(a=>a.id!==id||(!a.isNew&&!a.can_delete)));
  const clear=()=>canDelete&&change(items=>items.some(a=>!a.isNew&&!a.can_delete)?items:[]);
  const applyPredictions=(predictions:Prediction[])=>canCreate&&permissions.canReviewPredictions!==false&&change(items=>{
    const used=new Set(items.map(a=>a.prediction_id));
    const pending=predictions.filter(p=>{
      if(p.status!=='PENDING'||used.has(p.id))return false;
      used.add(p.id);return true;
    });
    return [...items,...pending.map(p=>({id:nextId.current--,isNew:true,class_id:p.mapped_class_id??0,
      class_name:p.mapped_class_name??p.model_class_name,annotation_type:p.prediction_type,x:p.x,y:p.y,width:p.width,height:p.height,
      points:structuredClone(p.points??null),source:'ai_accepted',prediction_id:p.id,prediction_token:p.draft_token}))];
  });
  const beginChange=()=>{const current=stateRef.current;if(editable&&!savingRef.current&&!current.transaction)write({...current,transaction:structuredClone(current.items)});};
  const commitChange=()=>{
    const current=stateRef.current;if(!current.transaction)return;
    const changed=!equal(current.items,current.transaction);
    write({...current,transaction:null,history:changed?[...current.history,current.transaction].slice(-50):current.history});
  };
  const cancelChange=()=>{const current=stateRef.current;if(current.transaction)write({...current,items:structuredClone(current.transaction),transaction:null});};
  const canRestore=(target:DraftAnnotation[])=>{
    const current=stateRef.current;
    if(!editable||savingRef.current||current.transaction)return false;
    const before=new Map(current.items.map(a=>[a.id,a])),after=new Map(target.map(a=>[a.id,a]));
    return current.items.every(a=>after.has(a.id)||(a.isNew?canCreate:canDelete&&a.can_delete))
      &&target.every(a=>{const now=before.get(a.id);return now?(same(a,now)||(canUpdate&&(now.isNew||now.can_edit))):
        a.isNew?canCreate&&(a.prediction_id===undefined||permissions.canReviewPredictions!==false):canDelete&&!!current.original.find(o=>o.id===a.id)?.can_delete;});
  };
  const target=state.history[state.history.length-1];
  const canUndo=!!target&&canRestore(target);
  const undo=()=>{
    const current=stateRef.current,previous=current.history[current.history.length-1];
    if(!previous||!canRestore(previous))return false;
    write({...current,items:structuredClone(previous),history:current.history.slice(0,-1)});return true;
  };
  const dirty=useMemo(()=>state.items.length!==state.original.length||state.items.some(a=>a.isNew||!state.original.some(b=>b.id===a.id&&same(a,b))),[state.items,state.original]);
  const payload=(expectedRevision?:number)=>({
    expected_versions:Object.fromEntries(stateRef.current.original.map(a=>[a.id,a.version??1])),
    ...(expectedRevision===undefined?{}:{expected_revision:expectedRevision}),
    items:stateRef.current.items.map(a=>({id:a.isNew?undefined:a.id,class_id:a.class_id,annotation_type:a.annotation_type,x:a.x,y:a.y,width:a.width,height:a.height,points:a.points??undefined,
      ...(a.isNew&&a.prediction_id!==undefined?{prediction_id:a.prediction_id,prediction_token:a.prediction_token}:{})}))
  });
  const persist=async<T,>(run:()=>Promise<T>,saved:(result:T)=>Annotation[])=>{
    if(savingRef.current)throw new Error('Save already in progress');
    if(stateRef.current.transaction)throw new Error('Finish the current gesture before saving');
    const currentImage=imageId;
    savingRef.current=true;setSaving(true);
    try{const result=await run();if(imageRef.current===currentImage)reset(saved(result));return result;}
    finally{savingRef.current=false;setSaving(false);}
  };
  const save=(expectedRevision?:number)=>persist(async()=>(await api.put<Annotation[]>(`/images/${imageId}/annotations`,payload(expectedRevision))).data,result=>result);
  const submit=(review:ReviewDetail,negative:boolean)=>persist(async()=>(await api.post<{annotations:Annotation[];review:ReviewDetail}>(`/images/${imageId}/review/submit`,{
    expected_revision:review.revision,expected_review_version:review.review_version,negative_confirmed:negative,annotations:payload(review.revision)})).data,result=>result.annotations);
  return {items:state.items,dirty,saving,canUndo,undo,historyLength:state.history.length,update,add,remove,clear,applyPredictions,
    beginChange,commitChange,cancelChange,replace:reset,save,submit};
}
