import {useEffect} from 'react';
import {api} from '../services/api';
let tabClientId:string|undefined;
let sequence=0;

export function useAnnotationActivity(imageId:number,enabled:boolean,idleSeconds=60){
  useEffect(()=>{
    if(!enabled)return;
    const clientId=tabClientId??(tabClientId=crypto.randomUUID());let lastActive=performance.now(),lastPulse=performance.now();
    let sending=false,disposed=false;
    const active=()=>{lastActive=performance.now();};
    const visibility=()=>{lastPulse=performance.now();};
    const pulse=async()=>{
      const now=performance.now(),elapsed=Math.min(15,Math.max(0,(now-lastPulse)/1000));lastPulse=now;
      if(disposed||sending||document.visibilityState==='hidden'||now-lastActive>idleSeconds*1000)return;
      sending=true;
      try{await api.post(`/images/${imageId}/activity`,{client_id:clientId,sequence:++sequence,elapsed_seconds:elapsed});}catch{/* Activity estimates never block annotation work. */}finally{sending=false;}
    };
    for(const event of ['pointerdown','pointermove','keydown','wheel'])window.addEventListener(event,active,{passive:true});
    document.addEventListener('visibilitychange',visibility);
    void pulse();const timer=window.setInterval(()=>void pulse(),10000);
    return()=>{disposed=true;window.clearInterval(timer);for(const event of ['pointerdown','pointermove','keydown','wheel'])window.removeEventListener(event,active);document.removeEventListener('visibilitychange',visibility);};
  },[imageId,enabled,idleSeconds]);
}
