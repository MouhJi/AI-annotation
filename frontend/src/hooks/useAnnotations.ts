import {useEffect,useMemo,useRef,useState} from "react"; import {Annotation,DraftAnnotation} from "../types"; import {api} from "../services/api";
const same=(a:DraftAnnotation,b:Annotation)=>["class_id","annotation_type","x","y","width","height"].every(k=>a[k as keyof DraftAnnotation]===b[k as keyof Annotation])&&JSON.stringify(a.points??null)===JSON.stringify(b.points??null);
export function useAnnotations(imageId:number, initial:Annotation[]) {
 const savingRef=useRef(false);const [saving,setSaving]=useState(false);const nextId=useRef(-1);
 const [items,setItems]=useState<DraftAnnotation[]>(initial); const [original,setOriginal]=useState(initial); const dirty=useMemo(()=>items.length!==original.length||items.some(a=>a.isNew||!original.some(b=>b.id===a.id&&same(a,b))),[items,original]);
 useEffect(()=>{setItems(initial);setOriginal(initial)},[imageId,initial]);
 const update=(id:number,change:Partial<DraftAnnotation>)=>setItems(v=>v.map(a=>a.id===id?{...a,...change}:a));
 const add=(box:Omit<DraftAnnotation,"id"|"isNew">)=>{const id=nextId.current--;setItems(v=>[...v,{...box,id,isNew:true}])};
 const remove=(id:number)=>setItems(v=>v.filter(a=>a.id!==id));
 const replace=(next:Annotation[])=>{setItems(next);setOriginal(next)};
 const save=async()=>{
   if(savingRef.current)throw new Error("Save already in progress");
   savingRef.current=true;setSaving(true);
   try {
   const saved:Annotation[]=(await api.put(`/images/${imageId}/annotations`,{
     expected_versions:Object.fromEntries(original.map(a=>[a.id,a.version??1])),
     items:items.map(a=>({id:a.isNew?undefined:a.id,class_id:a.class_id,annotation_type:a.annotation_type,x:a.x,y:a.y,width:a.width,height:a.height,points:a.points??undefined}))
   })).data;
   setItems(saved); setOriginal(saved); return saved;
   }finally{savingRef.current=false;setSaving(false)}
 };
 return {items,dirty,saving,update,add,remove,replace,save};
}
